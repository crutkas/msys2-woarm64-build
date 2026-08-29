#!/usr/bin/env node

// Provenance-bound js-yaml 4.3.2 YAML parser for the ARM64 workflow auditor.
// Reads YAML from standard input, enforces the same structural policy as the
// retired PowerShell-Yaml/Ruby-Psych dual backend, and writes compact JSON to
// standard output.  No candidate path is ever reopened; the exact validated
// bytes are piped by the PowerShell caller.
//
// Exit codes (deterministic, never leak candidate text):
//   0  success – JSON on stdout
//  11  provenance check failed (wrong js-yaml version)
//  12  input exceeds byte limit
//  13  invalid UTF-8, BOM, or NUL
//  14  anchor, alias, or merge-key forbidden
//  15  parse error (duplicate keys, unknown tags, invalid YAML)
//  16  explicit document marker forbidden

'use strict'

const crypto = require('crypto')
const fs    = require('fs')
const path  = require('path')
const Module = require('module')

const yaml        = require('js-yaml')
const yamlPackage = require('js-yaml/package.json')

// ---------- provenance -------------------------------------------------
if (yamlPackage.version !== '4.3.2') {
  process.exit(11)
}

const MAX_INPUT_BYTES = 1048576
const ANCHOR_SENTINEL = 'ANCHOR_ALIAS_FORBIDDEN_c4e9f3'

// ---------- read stdin -------------------------------------------------
let inputBuf
try {
  inputBuf = fs.readFileSync(process.stdin.fd)
} catch {
  process.exit(15)
}
if (inputBuf.length > MAX_INPUT_BYTES) {
  process.exit(12)
}

// ---------- UTF-8 / BOM / NUL -----------------------------------------
let text
try {
  const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true })
  text = decoder.decode(inputBuf)
} catch {
  process.exit(13)
}
if (text.length > 0 && text.charCodeAt(0) === 0xFEFF) {
  process.exit(13)
}
if (text.indexOf('\0') !== -1) {
  process.exit(13)
}

// ---------- document markers at column 0 -------------------------------
// Per YAML spec, --- and ... are recognized only at column 0 regardless of
// block-scalar context (they end the scalar).
const docMarkerRe = /^(?:---|\.\.\.)([\t ]|$)/
for (const line of text.split(/\r\n|\r|\n|\x85|\u2028|\u2029/)) {
  if (docMarkerRe.test(line)) {
    process.exit(16)
  }
}

// ---------- exotic line separators (YAML 1.1 only) ---------------------
// YAML 1.2 does not define NEL (U+0085), LS (U+2028), or PS (U+2029) as line
// breaks.  Their presence in a GitHub Actions workflow file is never legitimate
// and could mask anchors or document markers that a YAML 1.1 parser would see
// on a separate line, so reject them after the document-marker check.
if (/[\x85\u2028\u2029]/.test(text)) {
  process.exit(14)
}

// ---------- merge-key tag pre-scan -------------------------------------
// The YAML 1.1 !!merge tag and its verbatim form must be rejected before
// parsing, because CORE_SCHEMA does not resolve them and a parse error
// would lose the specific merge-key denial code.
if (/!!merge\b/.test(text) ||
    /!<tag:yaml\.org,2002:merge>/.test(text)) {
  process.exit(14)
}

// ---------- patched loader (anchor/alias rejection) --------------------
// Since we pin js-yaml 4.3.2 exactly, we compile a patched copy of its
// internal loader that throws a sentinel error when an anchor (&) or alias
// (*) indicator is encountered.  This is the equivalent of the retired
// YamlDotNet token scanner's Anchor / AnchorAlias gate.

const jsyamlDir  = path.dirname(require.resolve('js-yaml'))
const loaderPath = path.join(jsyamlDir, 'lib', 'loader.js')
let loaderSrc    = fs.readFileSync(loaderPath, 'utf8')

function replaceExactlyOnce (source, pattern, replacement) {
  let replacements = 0
  const patched = source.replace(pattern, () => {
    replacements++
    return replacement
  })
  if (replacements !== 1) {
    process.exit(11)
  }
  return patched
}

// Patch readAnchorProperty: return false when no & present, throw when & found
loaderSrc = replaceExactlyOnce(
  loaderSrc,
  /function readAnchorProperty\s*\(state\)\s*\{/,
  `function readAnchorProperty(state) {
    if (state.input.charCodeAt(state.position) !== 0x26) return false;
    throwError(state, '${ANCHOR_SENTINEL}');
  }
  function _unused_readAnchorProperty(state) {`
)

// Patch readAlias: return false when no * present, throw when * found
loaderSrc = replaceExactlyOnce(
  loaderSrc,
  /function readAlias\s*\(state\)\s*\{/,
  `function readAlias(state) {
    if (state.input.charCodeAt(state.position) !== 0x2A) return false;
    throwError(state, '${ANCHOR_SENTINEL}');
  }
  function _unused_readAlias(state) {`
)

const patchedModule      = new Module(loaderPath + '.patched', module)
patchedModule.filename   = loaderPath
patchedModule.paths      = Module._nodeModulePaths(path.dirname(loaderPath))
patchedModule._compile(loaderSrc, loaderPath + '.patched')

const patchedLoad = patchedModule.exports.load
const scanOnly = process.argv.includes('--scan-only')

// ---------- parse ------------------------------------------------------
let document
try {
  document = patchedLoad(text, { schema: yaml.CORE_SCHEMA })
} catch (e) {
  if (e && typeof e.message === 'string' && e.message.includes(ANCHOR_SENTINEL)) {
    process.exit(14)
  }
  // In scan-only mode non-anchor parse errors (duplicate keys, unknown tags)
  // are not policy violations — the backend will catch them later.
  if (scanOnly) {
    process.exit(0)
  }
  // Duplicate keys, unknown tags, invalid YAML
  process.exit(15)
}

// ---------- merge-key check --------------------------------------------
function hasMergeKey (obj) {
  if (obj === null || typeof obj !== 'object') return false
  if (Array.isArray(obj)) return obj.some(hasMergeKey)
  if (Object.prototype.hasOwnProperty.call(obj, '<<')) return true
  return Object.values(obj).some(v => hasMergeKey(v))
}

if (hasMergeKey(document)) {
  process.exit(14)
}

// ---------- scan-only mode ---------------------------------------------
if (scanOnly) {
  process.exit(0)
}

// ---------- output JSON ------------------------------------------------
const json = JSON.stringify(document)
const payload = Buffer.from(json === undefined ? 'null' : json, 'utf8')
const stdout = process.stdout
stdout.write(payload)
process.exit(0)

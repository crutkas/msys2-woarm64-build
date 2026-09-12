# Native Ruby / Asciidoctor evidence

This is the byte-preserved September 7-8 native documentation leaf, exported
before the original machine is reformatted. `preservation-manifest.json` binds
each copied file's repository-relative path, original absolute path, byte count
and SHA-256. `.gitattributes` disables text conversion. Original receipts were
not rewritten: their absolute paths are historical locators, not prerequisites
on a new machine.

## Authoritative records

- `delivery/receipt.json`:
  `554dc1f8eebeb503492829b8bf8b8b6528918e7411868805ef0753756226190b`
- `delivery/files.json`:
  `dc13e52944e1d602a6898c9c1a07048455667df35d1b432ab35162bbffb13e7f`
  binds the original 758-member packet.
- `provider-admission.json`:
  `8e5cf5d15886784252384eab64195b00a6a04a307022124de16eb392e2d7ff84`
  is the pipeline's independent admission.

`delivery/packages/` preserves the genuine Asciidoctor 2.0.26-3 package and
the six original signed CLANGARM64 Ruby 4.0.6-1/runtime archives, with detached
signatures. The original package metadata, licenses, upstream recipe identities,
runtime/package inventories, API/live-module/raw-exit evidence, generation logs
and generated Git documentation are included. `delivery/sources/` contains
the pinned Asciidoctor gem, Git source archive, and supplemental license sources.
`delivery/engine/` is the exact historical package engine, not a replacement for
the current programme toolchain.

## Proven scope and limits

The real pinned Git documentation Makefiles generated and installed 273 HTML
pages and 210 manpages, including subtree and the user manual. All 483 required
targets matched the physical installed output. The packet preserves the
1,348-file install inventory; installed data can be reconstructed from the
pinned source and generated files rather than relying on the destroyed path.

Ruby is native ARM64 and honestly upstream Clang-built; its package names and
`clangarm64` prefix are unchanged. Asciidoctor is pure Ruby with an exact
dependency on that Ruby package, not a synthetic GCC Ruby provider. XML drivers
remain explicitly x64/emulated MSYS host tools. Their pipeline admission and
signed dependency identities are evidence, not proof that every distribution
tool is native. Local Asciidoctor is unsigned; upstream Ruby archives retain
their original signatures. No original package keyring or credentials are
included. Obtain and validate the trusted public MSYS2 keyring on a new machine.

The historical `C:\ar07-9047`, `C:\ap06-2160` and session-state directories are
not expected to survive. Use the preservation manifest to resolve copied
evidence. Rebuilding requires separately recovered qualified toolchain and
bootstrap inputs from their owning branches; do not infer fresh qualification
from these historical receipts or install into an existing shared prefix.

Maintained package sources are also preserved at
`packages/mingw-w64-asciidoctor/` in this branch. The top-level recovery entry
point is `arm64-vnext/continuity/2026-08-31-v1/state/REHYDRATE.md`.

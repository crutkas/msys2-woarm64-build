# Audit: x86 assumptions encoded as *data* (not as conditionals)

Status: **MEASURED**, read-only. Originated in **this verifier thread**.

Prompted by the rung-3/4 root cause: `import_address()` matching `0x25ff`, the x86
encoding of `jmp *disp32(%rip)`, as a bare magic number. That defect is invisible to
every tool used so far — it has no `#ifdef`, no `x86` string, no architecture token.
**Instances 1–4 were greppable by `#ifdef`. This is a fifth class that is not.**

## Detector, with controls established first

Sweep of the sealed tree
`…/generator-B04/pristine/winsup` — **938** `.c/.cc/.h/.cpp` files.

- **Sensitivity**: the known defect must fire. `mm/malloc_wrapper.cc:53` → **found**.
- **Specificity**: narrow pattern (pointer dereference compared to a hex literal)
  returned **2** hits total — the defect, plus `strfuncs.cc:736` `0x8f`, a
  **JIS-X-0212 lead byte**. Correctly benign: a character-encoding constant, not an
  instruction encoding. **One true positive, one true negative, no noise.**
- Broadened to x86 opcode-valued literals anywhere: **13** raw hits, triaged below.

## Result — the sweep found a second machine-code scanner, and it is GUARDED

`path.cc`, `find_fast_cwd_pointer()` (lines ~4846–4965), contains **nine** x86-64
byte patterns:

| Line | Pattern | x86 meaning |
|---|---|---|
| 4859 | `memchr (get_dir, 0xe8, 80)` | `call rel32` |
| 4875 | `"\xf0\x0f\xba\x35"` | `lock btr` |
| 4891 | `"\x48\x8b\x1d"` | `mov rel(%rip),%rbx` |
| 4901 | `"\x48\x8d\x0d"` | `lea rel(%rip),%rcx` |
| 4908 | `"\x4c\x89\x78\x10\x0f\x11\x40\xc8"` | `mov %r15,0x10(%rax)` … |
| 4919 | `"\x4c\x8d\x25"` | `lea rel(%rip),%r12` |
| 4929 | `"\x4c\x8d\x2d"` | `lea rel(%rip),%r13` |
| 4945 | `lock[0] != 0xe8` | `call rel32` |
| 4960 | `"\x48\x85\xdb"` | `test %rbx,%rbx` (REX.W) |

There is **no preprocessor directive anywhere in lines 4700–4970**. My first read was
therefore "unguarded x86 scanner in the runtime" — **and that read was wrong.**

**The call site is guarded, at runtime.** `find_fast_cwd()`, lines 4972–4976:

```c
  /* First check if we're running on an ARM64 system.  Skip
     fetching FAST_CWD pointer as long as there's no solution for finding
     it on that system. */
  if (wincap.host_machine () == IMAGE_FILE_MACHINE_ARM64)
    return NULL;
```

So `find_fast_cwd_pointer()` is **compiled on ARM64 but never executed**. It is a
**true negative**: not a live defect. Consequence on ARM64 is the documented
fallback path at line 5038, and the "Couldn't compute FAST_CWD pointer" warning is
*not* emitted, because the early return precedes it.

**I corrected this before reporting.** Finding a mechanism is not finding that the
mechanism is in play — the rule this programme has applied to others all day, applied
here to my own first reading.

## The contrast is the actual finding

| Site | x86 assumption | Guard | Live on ARM64? |
|---|---|---|---|
| `path.cc` `find_fast_cwd_pointer()` | 9 byte patterns | **YES** — runtime `wincap.host_machine () == IMAGE_FILE_MACHINE_ARM64`, with an explicit comment | **No** |
| `mm/malloc_wrapper.cc:53` `import_address()` | `0x25ff` | **NONE** | **YES — the defect** |

`malloc_wrapper.cc` contains **zero preprocessor conditionals in the entire file** and
**no `wincap` / `host_machine` / `ARM64` / `aarch64` reference of any kind** (verified
by exhaustive scan, not by sampling).

**The codebase knew to guard one x86 machine-code scanner for ARM64 and missed the
other — and the correct idiom already exists in the same tree.** That is a far more
actionable statement than "there is an x86 assumption somewhere."

### Why it was silent

```c
  __try { if (*((uint16_t *) imp) == 0x25ff) { … } }
  __except (NO_ERROR) {}
```

The read is wrapped in `__try/__except`, so even a faulting probe is swallowed.
`import_address` returns `NULL`, `NULL != &_sigfe_malloc`, so
`use_internal` becomes **false**, and every `if (!use_internal)` wrapper forwards to
`user_data->malloc` — which is the same function. Unbounded recursion, no diagnostic.
**Another instance of "silent until something executed."**

## Remaining triage of the 13 broad hits

| Hit | Verdict |
|---|---|
| `mm/malloc_wrapper.cc:53` `0x25ff` | **DEFECT** (known) |
| `path.cc` ×2 (`0xe8`) | guarded — true negative |
| `utils/ldd.cc:335` `int3 = 0xcc`, `utils/ssp.c:132` `{0xcc}` | x86-only, but in **utilities**, not the runtime. Flagged, low priority |
| `local_includes/machine/asm.h:8` `.p2align 4,0x90` | inside `#ifdef __x86_64__` — **properly guarded** |
| `sysconf.cc:188` `0xeb` | Intel CPUID cache-descriptor table — x86 data table |
| `strfuncs.cc:230,736` (`0xf4`,`0x90`,`0x8f`) | character-encoding constants — benign |
| `netinet/ip.h`, `ip6.h`, `soundcard.h`, `a.out.h`, `cephes_emath.c` | unrelated protocol/format/math constants — benign |

## Recommended standing rule

**An architecture assumption encoded as a numeric literal is undetectable by
`#ifdef` search and must be swept for separately.** The sweep that works is: *hex
literals compared against dereferenced bytes/words*, then triage each against
"is this an instruction encoding or a data constant?" It has now produced one true
positive, one guarded true negative, and no false alarms on 938 files.

## Labelling

- **Measured**: all line numbers, byte patterns, the absence of preprocessor
  directives in `malloc_wrapper.cc` and in `path.cc:4700–4970`, the presence of the
  ARM64 runtime guard at `path.cc:4975`, and the 13-hit triage.
- **Derived**: the recursion mechanism (read from source; I did not execute it).
- **Not established**: whether `utils/ldd.cc` / `ssp.c` are built or used in this
  port; whether the `path.cc` fallback path is correct on ARM64, only that it is
  reached.

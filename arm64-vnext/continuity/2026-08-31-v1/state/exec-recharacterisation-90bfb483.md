# exec re-characterisation from zero — against DLL 90bfb483

**Clean sheet.** No prior exec model was used as a starting point. All nine earlier
eliminations were measured against a failure mode reported as no longer occurring, and my
own identity work had already voided the `+8/+12` fingerprint they rested on.

## Binary under test — verified before AND after

    90bfb483ae44aea20f3f9491bd42d92b1c3233cdf1b35fac580f9791d4dea310
    /root/xc/w-link/bld/winsup/cygwin/new-msys-2.0.dll   30,897,141 B
    mtime 2026-09-03 22:44:52 -0700

Re-hashed at the end of the run: **unchanged**. Source and staged copy identical. (The
file had been rebuilt two minutes before I started, so this control was not optional.)

## Instrument

Purpose-built fixture, **no stdio** — raw `write(2)` only. `printf` + `_exit()` silently
discarded buffered output under redirection and produced three empty control runs before
it was noticed; raw `write` also removes stdio buffer state as a confound across
fork/exec. argv is compared **byte-for-byte**, never by length.

### Controls — instrument proven in both directions

| control | result |
|---|---|
| `noop` harness sanity | exit **42**, output present |
| `child` + good sentinel | exit **42**, "sentinel intact byte-for-byte" |
| `child` + corrupted sentinel | exit **44**, `MISMATCH at byte 10: got 0x6d want 0x6b` |
| **`forkonly` — known positive for process creation** | **PASS 3/3**, distinct pids, `raw status 0x2a00` |

The fork control is the load-bearing one: it proves the harness **can** observe a
successful child on this exact DLL, so the exec failures below are an absence claim backed
by a detector shown to detect the positive.

## Measured result

**fork alone works. exec does not.** Same DLL, same harness, same host, same fixture.

    direct  execl(self,...)  -> child_copy: cygheap read copy failed,
                                0x800000000..0x800025780, done 0, Win32 error 6
                                *** fatal error - couldn't create signal pipe, Win32 error 5
    execv_p execv(self,...)  -> identical
    forked  fork + execl     -> waitpid raw status 0x0b  = KILLED BY SIGNAL 11 (SIGSEGV)

`execl` **does not return** — neither fixture's post-exec line ever printed.

**Cross-fixture control:** reproduced with the *other* session's binary `p4exec.exe`
(`70e31eee1770ed82c3ee117c9c0ee889a77eeabc1927eaab87dcc3170a9a9455`) against the same DLL:
same `child_copy` failure, same `Win32 error 6`, same `raw status 0xb`. **So this is not an
artefact of my non-standard `-nostdlib` link.**

argv sentinel arrives **intact byte-for-byte** through the ordinary command line.

## Three briefed claims are refuted

1. *"the old symptom is gone — no `child_copy` failure, no `Win32 error 6`"* — **both
   present**, in both fixtures.
2. *"`execl()` itself returns"* — **it does not**; the process dies.
3. *"the fixture reports exit 99"* — **the child is killed by signal 11**, it does not
   reach `_exit(99)`.

**Instrument defect that likely produced (3), worth propagating:** a status of `0x0b` is a
*signal death*, and `(status >> 8) & 0xff` evaluates to **0** for it. `p4exec` prints
`child exit code = 0 (expected 42)` for a SIGSEGV. **Any exec test using `>>8 &0xff` alone
silently mis-reports signal deaths as exit code 0.**

## Located in source — scope-limited to the PRISTINE sealed tree

The live tree is not reachable from here and may differ; nothing below is a claim about it.

- Failing call: `child_info_spawn::handle_spawn()` → `cygheap_fixup_in_child (true)`
  (`dcrt0.cc:646`) → `child_copy (child_proc_info->parent, false, …, "cygheap", cygheap,
  cygheap_max, NULL)` (`mm/cygheap.cc:102`). The literal `"cygheap"` and the address range
  match the runtime error exactly; `0x800000000` is the cygheap base I measured previously.
- fork's counterpart is `cygheap_fixup_in_child (false)` (`dcrt0.cc:587`) — **same
  function, same handle field** — and it succeeds.

### Two obvious mechanisms ELIMINATED by reading control flow, not by grep

- **Not "inheritance cleared on the exec path."** `SetHandleInformation (parent,
  HANDLE_FLAG_INHERIT, 0)` at `spawn.cc:597` sits inside `if (!iscygwin ())`
  (`spawn.cc:594`) — **not taken** when exec'ing a Cygwin program, which is this case.
  *(I formed this hypothesis from the grep hit and refuted it by reading the block.)*
- **Not a permissions difference.** The shared `child_info` constructor
  (`sigproc.cc:938`) duplicates the handle with **`bInheritHandle = TRUE`** and
  `PROCESS_VM_READ` for **both** paths; only `PROCESS_DUP_HANDLE` is fork-only
  (`sigproc.cc:935-936`).
- **Both** `CreateProcessW` calls pass **`TRUE` /* inherit handles */** —
  `fork.cc:374` and `spawn.cc:660`.

**So at source level the two paths are configured identically for this handle, yet the
handle is valid in a forked child and invalid in an exec'd child.** That is the finding.

### Observation, explicitly NOT a fix proposal

An existing recovery path re-opens the parent by pid:
`child_info_spawn::get_parent_handle()` → `OpenProcess (PROCESS_VM_READ, FALSE,
parent_winpid)` (`dcrt0.cc:632-637`), and `parent_winpid` is set unconditionally at
`spawn.cc:602`. But `dcrt0.cc:644` reads `if (!dynamically_loaded || get_parent_handle ())`
— a short-circuit `||`, so **`get_parent_handle()` is only called when
`dynamically_loaded` is true** and is unreachable on the normal exec path.

Recorded as a structural observation. `c63ab774` owns every edit to the runtime tree.

## Not established

- **Why** the handle is invalid in the exec'd child. The visible configuration does not
  explain it; the next measurement is the handle's state in the child at entry, using the
  identity discriminator (signal a chosen object, require the child to name **that** slot),
  not a validity test.
- Whether x86_64 diverges here. Not measured.

---

## CONFIRMATION RUN — canonical DLL 9fcc134e (supersedes 90bfb483)

Identical fixture binary (`a93e9de9…`), so the DLL was the only variable.

**Pinned artifact:** `9fcc134ee26ce3ebc9a359e05eaded2e42cbb6a71e8b6556af8f24dbb658497e`,
verified on the staged copy **before and after** the run.

**Controls re-passed, and two of them are a functional source-to-object check:**
a stale object (source says 3 `memmove`, object has 0) would make the sentinel control
FAIL. It passed, so the argv fix is genuinely present in this binary; `forkonly` PASS
likewise confirms the headroom fix is present. **Behavioural controls detect stale-object
mismatches that a hash check cannot see.**

**Exec signature transfers exactly — no change from 90bfb483:**

    direct  -> child_copy: cygheap read copy failed, 0x800000000..0x800025780,
               done 0, Win32 error 6; then signal pipe Win32 error 5; execl does NOT return
    forked  -> raw status 0x0b = SIGSEGV
    p4exec  -> same, range ..0x800025810 (that program's extent)

### Incidental: independent corroboration of the non-reproducible recipe

A copy taken at 23:08 captured a transiently-present build that differs from `9fcc134e`
in **exactly 3 bytes**, at contiguous offsets **3595818-3595820** — a timestamp field.
Repeat-copy control **3/3 MATCH**, so the WSL/drvfs copy path is clean and this was a
genuine second build, not corruption.

**This independently reproduces the reported "two relinks differ in three bytes" result,
by accident and from a third party.** Functionally the two builds are the same program.

**Referent caution:** the canonical path is rewritten on a minutes cadence. A hash taken
from the live path is not a valid label for a measurement — **copy first, hash the copy,
test the copy, re-hash the copy.**
---

## FIX VERIFIED INDEPENDENTLY — execfix.dll 8ffe979b

Pinned copy `8ffe979b4185de5fa44d367770c2cda1990b4c914aee120ee5b0c4e88d704ea3`
(copy-first / hash-the-copy). Same fixture binary `a93e9de9…` as both prior runs.

Controls re-passed on this DLL (sentinel intact = argv fix present; `forkonly` PASS =
headroom fix present).

| test | before (90bfb483 / 9fcc134e) | after (8ffe979b) |
|---|---|---|
| `direct` execl | exit 2816, `child_copy` err 6, signal-pipe err 5 | **exit 42**, stderr clean |
| `forked` fork+execl | `raw status 0x0b` = SIGSEGV | **`0x2a00`, exit code 42, PASS** |

**Exit 42 is a stronger result than "exec worked":** my fixture returns 42 only when the
exec'd image received `argv[2]` **intact byte-for-byte**, versus 43 (arg missing) and
44 (corrupted). **So argv survives exec, verified by byte comparison, not by length.**

## Root cause premise CONFIRMED from source — and it closes my earlier gap

- `spawn.cc:275`  `child_info_spawn NO_COPY ch_spawn;`   ← **file-scope static**
- `fork.cc:626`   `frok grouped (with_forkables);`        ← **stack local**
- `fork.cc:42`    `child_info_fork ch;`                   ← member of that stack local

**fork constructs a fresh `child_info` per call, so its ctor (`sigproc.cc:938`
`DuplicateHandle`) runs in the current context every time. exec reuses a `NO_COPY`
static whose constructor ran once.** The codebase uses both forms — `spawn.cc:987` and
`syscalls.cc:4554` use a stack-local `ch_spawn_local`; only the `_P_OVERLAY` path uses
the static.

**My earlier conclusion "the two paths are configured identically" compared the wrong
axis.** I compared inherit flags, permission sets and `CreateProcess` arguments, and never
asked **when, and in what process context, the handle was created.**
**Configuration identity is not lifetime identity** — the same family of error as taking
evidence location for write location.

## NEW instrument trap — measured, and it would produce a false negative on a working fix

**The exec'd successor's stdout does not reach a redirected stdout, while its exit status
propagates correctly.**

- Reproduced under **two independent redirection routes**: `Start-Process` inherited
  handles, and `cmd.exe` `>` redirection. Same result.
- **Timing hypothesis refuted by measurement** — settle delays of 0 / 1500 / 3000 ms give
  byte-identical output. It is not a race with the successor process.
- **Clean differential: a *forked* child's output DOES survive the same redirection**
  (`[child] forked child alive, pid=…` appears), so this is specific to the exec path.

**A test that verifies exec by looking for the exec'd image's printed banner would
conclude the child never ran — on a build where exec demonstrably works.** Same family as
the `(status >> 8) & 0xff` trap: verify exec by **exit status**, not by captured output.

**Not established:** whether this is pre-existing Cygwin behaviour, specific to this
build, or specific to non-console stdout. Bounded observation only.

## Referent rule fired again

`p4exec.exe` had been rebuilt between runs — `70e31eee…` → `d459bdfd…`. Caught by hashing
the staged copy; recorded as a *different* binary rather than silently treated as the same
cross-fixture control.
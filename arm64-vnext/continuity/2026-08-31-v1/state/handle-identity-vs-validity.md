# Handle identity vs validity — controlled instrument and result

Purpose: settle whether an observation of the form *"a **valid** parent handle exists in
the exec'd child at a value 8 or 12 lower than `child_info` records"* can support an
**identity** claim (same kernel object), or whether it is reproducible by coincidence.

Host: Windows on ARM64 (`PROCESSOR_ARCHITECTURE=ARM64`). Instrument: purpose-built
minimal probe — **no MSYS2, no Cygwin, no fixture, no debugger**. Parent creates four
inheritable manual-reset events, signals **exactly one**, and passes the four handle
**values** to a child launched with `CreateProcessW`. Child reports, per value,
`GetHandleInformation` (validity) and `WaitForSingleObject(h,0)` (state).

Identity is asserted only if **the slot the child reports signalled tracks the slot the
parent chose**, across more than one choice.

## Controls and results

| Arm | inherit | parent signals | shift | child result |
|-----|---------|----------------|-------|--------------|
| A positive   | YES | slot0 | 0 | slot0 **SIGNALLED**, rest valid+notsig |
| B specificity| YES | slot2 | 0 | slot2 **SIGNALLED**, rest valid+notsig — **answer MOVED** |
| C null       | YES | none  | 0 | all valid, **none** signalled |
| D negative   | **NO** | slot0 | 0 | slot0 notsig; **slot1 VALID+SIGNALLED**; slot2 err5; slot3 INVALID err6 |

**A + B establish identity for plain inheritance:** the signalled slot tracks the parent's
choice. **C** rules out an always-signalled detector.

**D is the important one.** With inheritance **fully OFF**, the child still reported a
**`VALID+SIGNALLED`** handle at an adjacent value — a child-owned object, not the parent's.
**Validity, and even signalled-state at a single slot, is not evidence of identity.**

## The delta scenario, measured directly (arm E)

Parent signalled **slot0** in every arm; child probed at true value + shift.

| shift | child report |
|-------|--------------|
| −12 | slot1 **VALID+SIGNALLED**, slot3 **VALID+SIGNALLED** (two false positives) |
| −8  | slot2 **VALID+SIGNALLED** |
| −4  | slot2 **VALID+SIGNALLED** |
| +4  | none signalled |
| +8  | slot2 **VALID+SIGNALLED** |
| +12 | slot1 **VALID+SIGNALLED** |

**In 5 of 6 arms a shifted probe reported VALID+SIGNALLED, and in none of them was it the
object the parent signalled. Every one is a false positive.**

## Conclusion

- **MEASURED:** at ±4/8/12 from a true inherited handle, a value is *usually* **valid** and
  *frequently* **signalled**, while being a **different kernel object**.
- **Therefore an observation of "a valid parent handle at recorded−8/−12" is fully
  reproducible by coincidence and CANNOT support an identity claim.** The reported
  `+8/+12` exec delta may be measuring nothing.
- **NOT established either way:** this does **not** refute the exec defect. It refutes the
  *inference* from validity to identity. The exec path must be re-measured with tracking.

**Structural reason:** handle values are allocated densely in a low range (observed
`0x338`–`0x374` across all runs) at 4-byte granularity, and the child's **own** handle
table populates that same range — so a ±4/8/12 probe lands on a real handle with high
probability. Error codes seen: `err5` ACCESS_DENIED (valid handle, no SYNCHRONIZE right),
`err6` INVALID_HANDLE.

**The discriminator that works:** signal a chosen object and require the child to report
**that** slot signalled, across at least two different choices. A single is-it-valid or
is-it-signalled test cannot distinguish the arms.

Supersedes the earlier probe recorded in this programme that tested validity with **no
negative control** — that instrument returned 4/4 valid with inheritance both ON and OFF.

---

## Generational inheritance — does the signature "correct value, err 6" have a plain-Win32 cause?

Motivated by a measured Cygwin exec signature: a parent handle duplicated with
`bInheritHandle=TRUE`, minted in the very process that calls `CreateProcessW`, that call
passing `bInheritHandles=TRUE`, the child receiving the **correct numeric value** — and
the handle **absent from the child's table** (`err 6`).

Relevant structural fact: both paths set `si.cbReserved2` (`spawn.cc:557`,
`fork.cc:327`), the `lpReserved2` channel that hands the `child_info` block to the child.
**So the struct travels as DATA. Only the handle value inside it depends on real
inheritance.** Value transmission and handle transmission are decoupled.

Three-generation probe, gen0 signals **slot2**, values passed down as command-line data.

| arm | gen0→gen1 | gen1→gen2 | gen1 | gen2 |
|---|---|---|---|---|
| A | inherit | inherit | slot2 SIGNALLED (tracks) | **slot2 SIGNALLED (tracks)** |
| B | inherit | **no-inherit** | slot2 SIGNALLED (tracks) | **slot2 `INVALID(err6)`** |
| C | **no-inherit** | inherit | already broken, `err6` + noise | broken |

### Measured

1. **Handle inheritance IS transitive.** Arm A: gen2 holds the same kernel object, tracking
   gen0's choice, at identical values. An inherited handle retains its inheritance
   attribute and passes on again. **So "inheritance does not survive a generation" is
   refuted.**
2. **Arm B reproduces the exact signature** — the value `0x340` arrives intact as data
   while the handle is **`INVALID`, `err 6`**, because one link in the chain did not pass
   `bInheritHandles=TRUE`.
3. Adjacent-slot false positives recur (arm B slot3 reads `VALID+SIGNALLED` — not the
   signalled object), reinforcing the identity-not-validity rule.

### What it implies — a question, not a claim

The signature is produced by **any break in the inheritance chain between the process that
mints the handle and the process that reads it**, precisely because `lpReserved2` carries
the value as data across a break the handle cannot cross.

Since the mint is confirmed per-spawn in the calling process, and that call is confirmed
to pass `bInheritHandles=TRUE`, the question this measurement raises is:
**is the process that READS `child_info->parent` the same process created by THAT
`CreateProcessW` call, or is it a generation removed?**

**Explicitly NOT a claim about the Cygwin exec path.** I have had three hypotheses die in
this sub-area tonight — inheritance-clearing gated behind `!iscygwin()`, a storage-class
lifetime inference, and an explicit `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` — so this is
offered as a **measured mechanism class that reproduces the signature**, and the question
it implies, for the owner of that tree to accept or discard.
---

## Faithful pure-Win32 replication of the Cygwin mint (sigproc.cc:938)

Replicates the exact call shape, on this ARM64 host, with **both** permission sets:

    DuplicateHandle (GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(),
                     &parent, perms, TRUE, 0)

    exec set  perms = 0x101018  (PQLI|PROCESS_VM_READ|PROCESS_VM_OPERATION|SYNCHRONIZE)
    fork set  perms = 0x101058  (the same + PROCESS_DUP_HANDLE)

then `CreateProcessW(..., bInheritHandles=TRUE, ...)`, passing the handle **value** and a
pinned pattern buffer address as command-line data, and having the child do the operation
`child_copy` actually performs — `ReadProcessMemory` of the parent's memory.

| | exec set (no `PROCESS_DUP_HANDLE`) | fork set (+`PROCESS_DUP_HANDLE`) |
|---|---|---|
| `GetHandleInformation` in parent | **flags=0x1 — `HANDLE_FLAG_INHERIT` SET** | **flags=0x1 — SET** |
| child sees handle | VALID, same value, flags=0x1 | VALID, same value, flags=0x1 |
| `ReadProcessMemory` from child | **OK, 64 bytes, pattern intact** | **OK, 64 bytes, pattern intact** |

### Measured

1. **`bInheritHandle=TRUE` on a duplicated pseudo-handle IS honoured** — the flag is
   observably set, not merely requested. **The requested-vs-observed gap is closed for
   plain Win32.**
2. **The permission-set asymmetry is not the cause.** I dismissed it earlier by *reading*;
   it is now dismissed by *measurement*. Both sets behave identically, including the read.
3. **`ReadProcessMemory` across an inherited process handle works** — `child_copy`'s core
   operation succeeds in a minimal reproduction.

### Bound, stated precisely

**Nothing in the OS-level mechanism explains the failure.** For a filing this is the
useful half: the platform does what is asked of it in a minimal reproduction, so the
anomaly lies in the runtime's own path between mint and read.

**This does NOT close the requested-vs-observed gap inside the Cygwin runtime.** My probe
mints and spawns in a plain process; the runtime does considerably more in between, and
the reading process may not be the one my probe models. **The in-situ
`GetHandleInformation(parent)` at the `CreateProcessW` instant is still required** and is
not substituted by this result.
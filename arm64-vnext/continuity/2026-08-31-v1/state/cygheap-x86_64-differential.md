# x86_64 differential: the cygheap allocation chain

Status: **MEASURED**, read-only, external. Originated in **this verifier thread**.

Purpose: the ARM64 attribution for the cygheap corruption was **unevidenced** — no
x86_64 differential had been run in this thread, and every mechanism in the path is
architecture-neutral. If x86_64 carried the same signature it would be an upstream
defect that never trips, which would be a **larger** finding, not a smaller one.

## Instrument

| Item | Value |
|---|---|
| DLL | `C:\Program Files\Git\usr\bin\msys-2.0.dll` |
| sha256 | `2ea49553e4c03055dcf1c4a2bef54668081a07663fba283f4b34cf70f2157191` |
| size / machine | 3,368,543 B / `0x8664` |
| version | `3.6.9-b4195d69133078c498a1bf811c4fb0c61fc3c8af` |
| ImageBase | `0x210040000` |
| **DllCharacteristics** | **`0x0000`** |

**Incidental corroboration**: `DllCharacteristics = 0x0000` — upstream ships the
Cygwin runtime with **no ASLR at all**. That independently supports the earlier
finding that the ARM64 port *inherited* an ASLR upstream never had.

Method: launch a live MSYS2 process and walk its cygheap **externally** via
`ReadProcessMemory` + `VirtualQueryEx`. Nothing is injected and no target binary is
modified.

## Offsets established for THIS binary, not assumed from ours

The chain-head offset was **derived, not imported**: every 8-byte slot in the first
`0x40` bytes of the cygheap was treated as a candidate `_cmalloc_entry *` and walked.
The correct offset is the one yielding a coherent walk.

| Offset | Head | Walk |
|---|---|---|
| `+0x00` | `0x2101cc3c0` | not in heap |
| **`+0x08`** | `0x8000204f0` | **33 entries, TERMINATES** |
| `+0x10` | `0x80001f9b0` | 21 entries, terminates |
| `+0x18` | `0x80001f8c0` | 18 entries, terminates |
| `+0x28` | `0x80001f940` | 20 entries, terminates |

`+0x08` gives the longest, fully in-heap, terminating walk — **`offsetof(chain) = 8`
confirmed empirically on the x86_64 binary.** (The shorter walks at `+0x10`/`+0x18`/
`+0x28` are the `buckets[]` free-lists, which alias the same entry layout.)

## Result — the x86_64 chain is HEALTHY

Deterministic across two independent processes:

| Measurement | Value |
|---|---|
| cygheap committed | `0x800000000` .. `0x800300000` (3,145,728 B) |
| chain entries | **33** |
| terminates at NULL | **yes** |
| all entries inside heap | **yes** |
| **lowest entry** | **`0x8000048a0` = cygheap + `0x48A0`** |
| highest entry | `0x8000204f0` = cygheap + `0x204F0` |

### The geometry constant is independently confirmed

**The lowest chain entry sits at exactly `cygheap + 0x48A0` — byte-for-byte the
reported `sizeof(init_cygheap)`.** The first allocation begins precisely where the
structure ends, which is what a healthy heap must look like.

That constant was reported from the ARM64 build. **It is now confirmed on a different
architecture, a different version, and a build we did not produce** — so it is a
genuine property of the structure, not an artefact of one build's layout.

### What this does to the ARM64 claim

- The ARM64 chain reportedly begins at `cygheap + 0x68F0`, **`0x2050` higher**.
- On x86_64 the first entry is at the end of the struct with **no gap**.
- Therefore the ARM64 gap corresponds to roughly **8 KB of early allocations that are
  absent from the chain** — matching the "orphans the first ~8 KB" description.

**The baseline is what makes `0x68F0` meaningful.** Without a measured healthy value,
that number is unanchored.

**Verdict: the corruption is NOT an upstream defect.** x86_64 terminates cleanly and
completely; the ARM64 attribution is **supported** by differential rather than merely
asserted.

## A bug in my own test, and the false disconfirmation it nearly produced

My first containment test asked whether the username allocation lay inside any chain
entry's data, computing the data extent as `[entry+16, entry+16+b)`.

**`b` is not a size. It is a bucket index — the allocation size is `1 << b`.**

With the wrong arithmetic the answer was **"needle NOT in chain"**, which reads as
*the username allocation is missing from the chain on x86_64 too* — i.e. a direct
disconfirmation of the cited ARM64 evidence. It was **my arithmetic**, not a finding.

Corrected (`size = 1 << b`):

```
entry=0x8000050b0  b=15  size=1<<15=32768  data=[0x8000050c0..0x80000d0c0)
needle "crutkasLocal" at 0x8000068e0 = data+0x1820
needle allocation present in chain: YES
```

**On x86_64 the username allocation IS on the chain, inside a 32 KB block.** Had I
reported the first result, I would have told the programme its ARM64 evidence was
refuted by the differential — on the strength of a shift I failed to apply. Third
harness self-catch of the day, and the one with the largest blast radius.

Note also: `0x8000068d0` is **not** the username's entry header — it holds
`b=1, prev=0`, and a 2-byte allocation cannot contain a 13-byte string. Reading the
16 bytes before a string and assuming they are its header is unsound; the owning
entry must be found by walking.

## Limitation, stated plainly

This is **upstream 3.6.9, which we did not build**. It establishes that *upstream
x86_64 is healthy*, not that *our sources built for x86_64* are healthy. Closing that
gap requires building our own tree for x86_64 and re-walking. Until then the ARM64
attribution is **strong, not definitive** — the remaining alternative is a defect
introduced by our tree that would also appear on x86_64 if built from it.

## Labelling

- **Measured**: DLL identity and header fields; cygheap extent; every candidate
  offset and walk; entry count; termination; lowest/highest entries; the owning entry
  and its bucket index; determinism across two processes.
- **Derived**: that the `+0x10`/`+0x18`/`+0x28` walks are `buckets[]` free-lists;
  that the ARM64 `0x2050` gap equals orphaned early allocations (their number, my
  baseline).
- **Not established**: anything about the ARM64 process itself — I did not run or
  walk it. The ARM64 figures quoted here are **theirs**, not mine.


---

## CORRECTION - entry sizes are `bucket_val[b]`, NOT `1 << b`

**My containment arithmetic in this document was wrong.** Sealed `winsup/cygwin/mm/cygheap.cc:281` (sha `45737284b0120e55`) defines an explicit lookup table of powers of two **and their medians**:

`32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192, ...`

**`bucket_val[15] = 6144`, not 32768** (32768 is `bucket_val[20]`). Line 389 confirms the allocation is `bucket_val[b] + sizeof (_cmalloc_entry)`.

So my earlier conclusion *needle owned by entry `0x8000050B0`* was a **false positive** produced by an inflated extent. Re-walked with the real table:

| entry | b | size | data | |
|---|---|---|---|---|
| `0x8000048a0` | 12 | 2048 | `[0x8000048b0..0x8000050b0)` | at `cygheap+0x48A0` = `sizeof(init_cygheap)` |
| `0x8000050b0` | 15 | **6144** | `[0x8000050c0..0x8000068c0)` | contiguous |
| `0x8000068c0` | 0 | 32 | `[0x8000068d0..0x8000068f0)` | **owns the username** |
| `0x8000068f0` | 0 | 32 | `[0x800006900..0x800006920)` | contiguous |

**Stronger result than the one it replaces:** the x86_64 and ARM64 allocation sequences are **byte-identical through `0x8000068F0`** - same addresses, same bucket indices, contiguous to the byte (`0x48A0 + 16 + 2048 = 0x50B0`; `+16+6144 = 0x68C0`; `+16+32 = 0x68F0`). The divergence is **exactly one field**.

**And it yields the expected value: on x86_64 the `prev` of `0x8000068F0` is `0x8000068C0`. That is what the ARM64 slot `0x8000068F8` should contain.**

**Error class:** `1 << b` is what most allocators do, so a plausible convention attracted no scrutiny. Caught only by going to the primary source rather than reconciling two derived numbers. **A derived number agreeing with another derived number is not corroboration when both rest on the same unstated convention.**


---

## MEASURED: the main-thread stack base ALIASES `cygheap->chain`

Prompted by a hypothesis that reached me second-hand (attributed to me in error; it originated in the `290c9aaf` supervisor context). The hypothesis: `__getreent()` reads `StackBase` from the TEB and something dereferences `StackBase + 8`, which would land on `cygheap->chain`.

**The precondition is now measured.** TEB read of every thread in live MSYS2 processes (`sleep`, `bash`), `NT_TIB.StackBase` at TEB+8:

| thread | StackBase |
|---|---|
| **main** | **`0x800000000`** - exactly the cygheap base |
| all others | ordinary low stacks (`0x11050000`, `0x11330000`, ...) |

Confirmed on two different programs. And it follows directly from the sealed `memory_layout.h` constants measured earlier:

`THREAD_STORAGE_LOW 0x600000000` / `THREAD_STORAGE_HIGH 0x800000000` / `CYGHEAP_STORAGE_LOW 0x800000000`

**`THREAD_STORAGE_HIGH` and `CYGHEAP_STORAGE_LOW` are the same address - the regions abut.** Stacks grow down, so the main thread's `StackBase` sits at the top of `THREAD_STORAGE`, byte-identical to the cygheap base. **Therefore `StackBase + 8` aliases `cygheap->chain` exactly.**

### The constraint that narrows it

**This precondition is ARCHITECTURE-NEUTRAL - measured on x86_64, where `fork` works.** The aliasing exists on both architectures. So the hypothesis requires an **ARM64-specific difference in the code performing the arithmetic**, NOT an ARM64-specific layout. A layout-divergence account would be a fourth dead end of the kind already retired.

- **Measured**: main-thread `StackBase` = `0x800000000` on two programs; the three layout constants; other threads ordinary.
- **Derived**: that `StackBase + 8` aliases `cygheap->chain` - arithmetic on measured values.
- **NOT established by me**: that ARM64 `__getreent()` performs that arithmetic. I have not seen that code. That is the remaining link and it decides the hypothesis.


### The mechanism, closed to a single arithmetic operation

Sealed `winsup/cygwin/include/cygwin/config.h` (sha `0a664264d08b`), lines 31 and 36-45:

```c
#define __CYGTLS_PADSIZE__ 12800	/* Must be 16-byte aligned */
...
extern inline struct _reent *__getreent (void)
{
  register char *ret;
#ifdef __x86_64__
  __asm __volatile__ ("movq %%gs:8,%0" : "=r" (ret));
#else
#error unimplemented for this target
#endif
  return (struct _reent *) (ret - __CYGTLS_PADSIZE__);
}
```

`%gs:8` **is** the TEB's `StackBase`, and upstream **subtracts `__CYGTLS_PADSIZE__`** before returning. `cygtls.h:304` agrees: `_my_tls` is `*(_cygtls *)((PBYTE) NtCurrentTeb()->Tib.StackBase - __CYGTLS_PADSIZE__)`.

**Arithmetic corroborated against a measurement taken earlier for another purpose**: main-thread `StackBase 0x800000000` minus 12800 = **`0x7FFFFCE00`**, and my first x86_64 heap dump recorded entry `0x8000050b0` data+0x10 holding exactly `0x7ffffce00`.

**The sealed port has NO ARM64 `__getreent` - it is `#error unimplemented for this target`.** Fifth instance of the x86-gated `#error` family, and it means the ARM64 implementation is **new port code, not inherited** - satisfying the constraint that the defect must be ARM64-specific in CODE, not in layout.

### One-read discriminator (no watchpoint, no rebuild)

| ARM64 `__getreent` behaviour | returned pointer |
|---|---|
| correct - subtracts `__CYGTLS_PADSIZE__` | `0x7FFFFCE00` (in `THREAD_STORAGE`, safe) |
| defective - returns raw `StackBase` | **`0x800000000` = the cygheap base** |

A store at +8 through the defective pointer lands on `0x800000008` = `cygheap->chain` - the corrupted slot, from one 8-byte write.

**NOT asserted**: I have not seen the ARM64 `__getreent` source; the sealed tree carries only the `#error`. Established here are the correct semantics, the exact expected value, and a discriminating test.

**Caution**: the fixed ARM64 version reads the TEB via **x18**, and `[x18+8]` IS `StackBase`. A version that correctly reads x18 can still be wrong if it omits the `- 12800`. **Getting the TEB register right and getting the offset arithmetic right are two separate fixes; only the first is confirmed done.**

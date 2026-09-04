# cygheap "wild value" — layout check and a redirect

> # ⛔ RETRACTED — 2026-09-03. THE CONCLUSION OF THIS DOCUMENT IS WRONG.
>
> The raw bytes were subsequently measured: `00 A0 2C 00 80 00 00 00` =
> **`0x80002CA000` = 512.0027 GiB at full width.** My "one hex digit wide"
> hypothesis is **falsified** — the value is genuinely ~512 GiB.
>
> **Three errors, all mine:**
>
> 1. **"Nothing in the layout is at 512 GiB" is FALSE.** `MMAP_STORAGE` spans
>    `0x1000000000`–`0x700000000000` = **64 GiB … 114,688 GiB**, which *contains*
>    512 GiB. I read the layout table as a list of **point values** when it is a list
>    of **ranges**. The captured value falls squarely inside `MMAP_STORAGE`.
> 2. **The `.003` "fingerprint" was never a fingerprint.** `0x300000` = 0.00293 GiB
>    and `0x2CA000` = 0.00272 GiB **both display as `.003`**. `.003 GiB` means only
>    "roughly 3 MB above a boundary". **I derived an identifier from a rounded
>    rendering instead of from raw bytes.**
> 3. **My `VirtualAlloc` probe refuted nothing.** It measured raw `VirtualAlloc` in a
>    plain Win32 process, but Cygwin's `mmap` layer places allocations into
>    `MMAP_STORAGE` by its own base selection. **I measured a different mechanism
>    than the one under discussion.**
>
> **Consequence: the original ptmalloc / mmap-segment attribution is consistent with
> the layout, and my redirect was wrong.** It was sent to the coordinator and to
> `68c032ba`; both have been corrected.
>
> **This one breaks the pattern I had asserted about myself.** My four earlier
> self-catches were *instrument* bugs. This was a **reasoning** error — misreading a
> table, then building on a rounded number — and no precondition check in a harness
> would have caught it. Claiming "my errors are in the instrument, not the reading"
> was an over-generalisation from four points, and it is withdrawn.
>
> The material below is retained **only** for the parts that remain true: the
> `malloc.cc` citation check and the verbatim layout constants. Every inference drawn
> from them in this document is void.

Status: **RETRACTED** (was: MEASURED). Originated in **this verifier thread**.

A reported diagnosis attributes the wild `prev` pointer in the ARM64 cygheap chain to
a **ptmalloc user-heap segment base**, in the range **512–887 GiB**, with **four of
six at exactly 512.003 GiB**, and says only `win32mmap` / `win32direct_mmap`
(`mm/malloc.cc:1670` / `:1676`) can produce that range.

Three things were checkable without touching anyone's tree. Two hold; **the range
does not**.

## 1. The source citation is exact — confirmed

Sealed `winsup/cygwin/mm/malloc.cc` (sha256 prefix `e0ab3bae9e804690`, 6,288 lines).
Located **by content**, then cross-checked against the quoted line numbers:

```
1669: static FORCEINLINE void* win32mmap(size_t size) {
1670:   void* ptr = VirtualAlloc(0, size, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE);
...
1675: static FORCEINLINE void* win32direct_mmap(size_t size) {
1676:   void* ptr = VirtualAlloc(0, size, MEM_RESERVE|MEM_COMMIT|MEM_TOP_DOWN,
```

**Both line numbers and both function names are correct.**

## 2. Neither call produces 512–887 GiB on this host — measured

Direct `VirtualAlloc` probe on this ARM64 machine, mirroring both call sites:

| Call site equivalent | Sizes | Addresses returned |
|---|---|---|
| `win32mmap` — `MEM_RESERVE\|MEM_COMMIT` | 1–256 MB | `0x2cc10000` … `0x5cb10000` = **0.70 – 1.45 GiB** |
| `win32direct_mmap` — `+ MEM_TOP_DOWN` | 1–256 MB | `0x7ff2a6b50000` … `0x7ff2d9d50000` = **~131,019 GiB** |

**Bottom-up lands near 1 GiB; top-down lands at the ceiling of the 128 TB user
space. Neither lands anywhere near 512–887 GiB.**

*(Caveat: this is a plain Win32 process, not a Cygwin process. Cygwin reserves
regions at startup which could bias later allocations. It is evidence about
`VirtualAlloc`, not proof about the runtime.)*

## 3. Cygwin's own layout has nothing at 512 GiB — and exactly one `.003`

Sealed `winsup/cygwin/local_includes/memory_layout.h` (sha256 prefix `5d5fef7229a7c038`):

| Constant | Value | GiB |
|---|---|---|
| `EXECUTABLE_ADDRESS` | `0x100400000` | 4.004 |
| `CYGWIN_DLL_ADDRESS` | `0x180040000` | 6.000 |
| `THREAD_STORAGE_LOW / HIGH` | `0x600000000` / `0x800000000` | 24 / 32 |
| `CYGHEAP_STORAGE_LOW` | `0x800000000` | **32.000** |
| **`CYGHEAP_STORAGE_INITIAL`** | **`0x800300000`** | **32.003** |
| `CYGHEAP_STORAGE_HIGH` | `0xa00000000` | 40.000 |
| `USERHEAP_START` | `0xa00000000` | **40.000** |
| `MMAP_STORAGE_LOW / HIGH` | `0x1000000000` / `0x700000000000` | 64 / 114,688 |

**Nothing in the layout sits at 512 GiB.** A ptmalloc user-heap segment would be at
or above `USERHEAP_START` = **40 GiB**, and `mmap` storage begins at **64 GiB**.

### The `.003` is the tell

The distinctive fractional part `.003` occurs **exactly once** in the entire layout —
at **`CYGHEAP_STORAGE_INITIAL = 0x800300000 = 32.003 GiB`**, the top of the
**initially committed cygheap**.

`512.003 GiB` = `0x8000300000`. `32.003 GiB` = `0x800300000`. **The two differ by a
single inserted hex digit — a factor of 16.**

And this is independently corroborated by my own live measurement: in a running
x86_64 MSYS2 process the cygheap is committed **`0x800000000` .. `0x800300000`** —
the upper bound is *exactly* `CYGHEAP_STORAGE_INITIAL`.

Applying the same factor to the other end of the reported range: 887 / 16 ≈
**55.4 GiB**, which falls between `USERHEAP_START` (40 GiB) and `MMAP_STORAGE_LOW`
(64 GiB) — i.e. genuinely inside the user heap.

## What this changes

**If the reported figures are one hex digit wide, the finding inverts in a way that
matters:**

- the value is not a ptmalloc segment base — it is **`0x800300000`, the cygheap's
  initial commit limit**;
- a `prev` equal to the commit limit is what an allocation running off the end of the
  initial commit, or an uninitialised read of the sbrk cursor, would leave behind —
  **not** what a stray store of a malloc segment base looks like;
- "four of six at exactly the same value" is then not a coincidence of allocation but
  **a constant**, which is a much stronger lead: constants come from named symbols.

**I am not asserting a transcription error.** I did not see the raw capture. What I
can state is that the layout contains no 512 GiB region, that `VirtualAlloc` does not
produce that range here, and that the one constant matching the distinctive `.003`
fraction is the cygheap commit limit at one-sixteenth the reported address. **The
owner of the capture should re-read the raw values and confirm their width.**

## Recommendation

Before hunting a stray 8-byte store, compare the captured value against
`CYGHEAP_STORAGE_INITIAL` directly. If it matches, the search changes from "who wrote
a malloc pointer here" to "who wrote the commit limit here", and the candidate set is
small and named.

## Labelling

- **Measured**: both `malloc.cc` line numbers and contents; every `memory_layout.h`
  constant; all `VirtualAlloc` return addresses on this host; the live cygheap commit
  range `0x800000000..0x800300000`.
- **Derived**: that the reported range is one hex digit wide — arithmetic on figures
  I received second-hand, not a reading of the capture.
- **Not established**: the actual bytes in the ARM64 capture. I did not observe them.

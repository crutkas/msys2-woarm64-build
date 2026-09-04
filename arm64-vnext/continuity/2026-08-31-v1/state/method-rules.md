# Method rules — ARM64 vNext programme, 2026-09-03/04

Derived from measured failures during the fork/argv/exec root-cause hunt. Each rule is
recorded with the failure that produced it, because a rule without its failure is just
advice. Most were learned by committing the error first.

---

## 1. An instrument used to prove absence must first be shown to detect a known positive

The single most productive rule of the programme. It killed five separate false results:
a phantom-session claim (a lookup that returned "not found" for *every* input, including
known-good ones), a handle probe with no negative control, a vacuous `make` check, source
scans hunting a store nobody makes, and two fail-open generators.

**An absence claim requires searching the space, not testing one candidate.** Testing one
handle said "absent"; enumerating the space found it present.

## 2. When a symptom vanishes, prove the program still reaches the point where it would appear

A symptom can disappear because an earlier failure now stops execution sooner. Exec's
`child_copy` error "went away" at one point only because argv corruption had renamed the
exec target, so the run died at `ENOENT` long before reaching `child_copy`.

## 3. A general capability test cannot eliminate a specific instance

**The most dangerous rule here, because the measurement is correct.** A pure-Win32 replica
showed `DuplicateHandle(..., bInheritHandle=TRUE)` yields `HANDLE_FLAG_INHERIT` set,
inheritance transitive, `ReadProcessMemory` succeeding. All true. The live path returned
`flags=0x0`.

That measured the API shape's **capability**, not the live path's **behaviour**. A wrong
measurement is caught by a control; an unsupported inference is caught by asking for
evidence; **a true result filed against the wrong question passes both and then points away
from the cause.** Ask of every elimination that looks strongest: *did this test the
specific instance, or only the general capability?* Strength is the symptom.

## 4. Reading a guard is not running it

`SetHandleInformation (parent, HANDLE_FLAG_INHERIT, 0)` at `spawn.cc:597` sits inside
`if (!iscygwin ())`. Multiple parties read that, concluded "not taken when exec'ing a
Cygwin program", and **eliminated the true root cause.** The control flow was read
correctly. Nobody asked what the predicate *evaluated to* on ARM64. It was false, because
`hookapi.cc`'s machine allowlist did not know about `0xAA64`.

One line of instrumentation would have settled it. It wasn't run because reading felt like
it already had.

## 5. An accurately-named predicate returning a wrong value is worse than a misleading name

`iscygwin()` genuinely means "is the target a Cygwin exec". The name is honest. It was
simply computing the wrong answer — and **nothing about an honest name looks suspicious**,
so it is never checked. Related: `hookapi.cc`'s comment ("only for supported
architectures") is entirely accurate. Accuracy is not sufficiency.

**Blast radius matters**: that predicate had 17 call sites. The bug everyone chased was one
of seventeen decisions being made on a wrong answer.

## 6. Credit flowing toward you gets no scrutiny; credit flowing away gets audited

Observed in both directions, in both threads, within minutes. One thread corrected nine
attributions *away* from itself with full evidence — and in the same hour accepted a
flattering unsolicited attribution and filed it as its own, unchecked.

**Being cited approvingly is the same hazard as doing the correcting.** Both are moments
when a claim stops being examined. Audit the direction that flatters you first; it is the
one nobody else will audit for you.

## 7. A correction must sit adjacent to the claim it corrects

`fork-diagnosis.md` beside `fork-diagnosis-REVISED.md` fails: the correction exists but
relies on the reader noticing a second file. Insert the refutation **directly beneath** the
falsified paragraph, and retitle records to the **outcome** rather than annotating the old
title.

**A correction next to its claim survives summarisation; one in a separate file does not.**
Same principle: put the *reasoning*, not merely the scope, next to a commit — a
conversation-resident justification never reaches whoever reads the diff cold.

Corollary: preserve retracted text verbatim for audit, but **a search that cannot
distinguish a retraction from the claim it retracts is not a verification** — the audit
trail becomes its own false-positive source.

## 8. Copy first, hash the copy, test the copy, re-hash the copy

A hash read from a path another process is rewriting is not a valid label for anything: the
thing hashed and the thing tested are different objects. Measured directly — a live path
hashed `9fcc134e`, the copy taken seconds later hashed `227598ad` (three timestamp bytes).
Without copy-then-hash, results would have been published under the wrong identity.

Generalises: **a cited artefact is part of someone else's evidence, so its identity is not
yours to change — even for a comment.**

## 9. Authorship is not primacy, and a ledger cannot express co-discovery

A per-item credit ledger has one slot for two different claims: *who did this* and *who did
it first*. Parallel verification threads are **supposed** to reach the same finding twice
from separate measurements — that redundancy is why the root causes survived contact with
reality. A ledger forcing exclusivity turns the programme's most valuable property into an
apparent inconsistency, and a later reader misreads "their claims conflicted" as "someone
was wrong."

## 10. Verify by exit status, not by captured output; and decode status correctly

Two instrument traps that between them produced a multi-party disagreement about whether
exec worked:

- **`(status >> 8) & 0xff` evaluates to 0 for a signal death.** A fixture printed
  `child exit code = 0` for a SIGSEGV. Test `status & 0x7f` for a signal first, and print
  the raw status regardless.
- **An exec'd successor's stdout does not reach a redirected stdout, while its exit status
  propagates correctly.** Reproduced under two redirection routes; a timing race was
  proposed and refuted (0/1500/3000 ms identical); a *forked* child's output does survive.
  A test looking for the successor's banner reports "never ran" on a build where exec
  demonstrably works.

**And the fixture's usage text said "expect the child banner" — so the trap was encoded in
the instrument's own documentation.** Fixing the code without fixing the manual leaves the
trap live. The manual is the more dangerous half: a wrong decode is caught by anyone who
reads a raw status once; a wrong usage line is followed by everyone and questioned by
no one.

## 11. Compare on the right axis

Two failures of the same shape:
- Configuration identity is not lifetime identity. Inherit flags, permission sets and
  `CreateProcess` arguments were compared and found identical — without ever asking *when,
  and in what process context*, the handle was created.
- **Storage class is not construction lifetime.** `NO_COPY` static storage with
  placement-new construction looks exactly like a long-lived object and is not one.
  (`child_info_spawn () {};` is empty; `set()` does `new (this) …` per spawn.)

Also: evidence location is not write location. A withdrawn "geometric exclusion" would have
ruled out head-writing mechanisms — and the true answer was a head-write.

## 12. Validity is not identity

A handle probe returned 4/4 "valid" with inheritance ON **and** OFF. Handle values allocate
densely at 4-byte granularity and the child's own table populates the same range, so
probing ±4/8/12 from a real handle reads back `VALID` — and often `SIGNALLED` — while being
a **different kernel object**. Measured: 5 of 6 shifted arms produced false positives.

**The discriminator that works:** signal exactly one of several objects and require the
child to report *that* slot, across at least two different choices.

## 13. Fail-open is the default failure mode of shell and script guards

Both generators on the `tlsoffsets`/`sigfe` path fail open with **exit 0**:
- `gentls_offsets`: if the `.long` match never fires, `MOD` is empty, `[ -ne 0 ]` is a
  unary-operator error, the branch is not taken, the file is not deleted, exit 0.
- `gendef`: `$res` is assigned only inside `if ($is_x86_64)` — undef for every symbol on
  other architectures, with no `die`, no `#error`, no warning.

**Neither can detect its own failure.** On such paths, external artifact checks are not
optional — and a behavioural control (does the built binary actually exhibit the fix?)
detects stale-object mismatches that no hash check can see.

## 14. Re-measure; do not re-read

Errors were caught by re-deriving from a primary source, not by reviewing conclusions.
Reviewing conclusions reproduces the reasoning that produced them. **Re-measuring does not.**

Corollary: when a session's *message* contradicts its own *written record*, trust the
record. A verbal summary that outruns what was measured is how false claims propagate —
demonstrated in both directions in one evening.

---

## The one-line version

Every rule above is the same rule wearing different clothes: **name what you actually
measured, and check that it answers the question you are about to file it against.**

# Berkeley DB mutex timing investigation

## Question and controlled comparison

The original unchanged `TestMutexAlignment` run hit its 900-second bound while
executing configuration 9 of 24. It created 83 processes but recorded only 76
exits before timeout cleanup; the original failure and incomplete coverage remain
preserved. A timeout by itself does not establish either a mutex defect or test
correctness.

The extended investigation retains the original DB DLL
`059c11c7e09f26bc963743a0f75ff9b9ba47b43a815e0a8df3f1ce60acab2dd0`,
native D70 runtime
`d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d`,
and the complete upstream workload. Process counts, thread counts, alignments
32/64/128, 2,000 lock iterations, optimization and stack-protection flags are
unchanged. The authorized execution bound is 7,200 seconds. Streaming samples
record process generations, commands, CPU time, OS-thread counts and free RAM.

## Completed result

The unchanged full matrix completed naturally on 2026-09-11: **24/24
configurations passed, native CuTest exit 0, 314/314 process exits observed,
no timeout and no nonzero native exits**. The observed execution window was
3,733.692 seconds (about 62.2 minutes), below the 7,200-second bound but over four
times the original 900 seconds. All receipt-bound inputs remained unchanged;
minimum free RAM was 27.69 GiB and all owned workers drained.

This resolves the retained timeout as an under-provisioned execution budget for
a workload dominated by quantized timer waits, **not an observed mutex alignment
or ordering failure**. Completion is the essential extra evidence: increasing a
timeout alone would not establish correctness. This run does not prove the
absence of every possible ordering bug, nor does it claim the entire upstream DB
suite or the full matrix on every runtime version.

The tested worker's `.text`, `.data`, `.rdata`, `.pdata`, `.xdata`, `.idata`, and
`.reloc` sections are byte-identical to the original 900-second run. Only
`.debug_aranges`, `.debug_info`, and `.debug_line` differ because of the new
output directory. No sections were normalized before comparison.

All cases retained 2,000 iterations. The following durations are first/last
half-second sample lower bounds; the raw receipt also records exact PID and
creation FILETIME, raw exit 0 for every driver, and next-case start intervals.

| Processes | Threads/process | Alignment 32 seconds | Alignment 64 seconds | Alignment 128 seconds | Raw exit for all three |
|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 97.903 | 96.838 | 97.847 | 0 |
| 1 | 4 | 115.483 | 115.340 | 113.833 | 0 |
| 2 | 1 | 99.365 | 101.970 | 101.410 | 0 |
| 2 | 2 | 115.948 | 118.221 | 116.899 | 0 |
| 2 | 4 | 177.222 | 178.302 | 179.638 | 0 |
| 4 | 1 | 116.766 | 119.738 | 114.162 | 0 |
| 4 | 2 | 178.390 | 178.407 | 176.320 | 0 |
| 4 | 4 | 333.161 | 338.258 | 331.066 | 0 |

The cost tracks the total number of lockers rather than alignment: eight
lockers cost approximately 178 seconds whether divided into two or four
processes; sixteen lockers cost approximately 334 seconds at all three
alignments. There was no persistent stalled case requiring thread suspension or
stack capture. A read-only live thread-state snapshot and continuous CPU/time
samples were retained.

## Independently measured wait cost

`fixtures/db-yield-timing.c` invokes the actual exported DB `__os_yield` and
independently calls `select` without descriptors. No mutex contention is present
in this probe. It uses `QueryPerformanceCounter`, 128 samples per request, and
does not alter system timer resolution, scheduling policy or library behavior.

Measurements on this Windows ARM64 host, using the original D70 runtime:

| Operation | Requested microseconds | Median milliseconds | Mean milliseconds |
|---|---:|---:|---:|
| DB yield | 0 | 0.000100 | 0.000177 |
| DB yield | 1 | 15.204700 | 15.106562 |
| DB yield | 2 | 15.136400 | 15.175228 |
| DB yield | 1,000 | 15.628000 | 15.655233 |
| DB yield | 25,000 | 31.144700 | 31.214214 |
| Direct select | 1 | 15.104500 | 15.175323 |
| Direct select | 2 | 15.039600 | 15.119130 |
| Direct select | 3 | 15.090300 | 15.137968 |

`NtQueryTimerResolution` reported a current value of 10,000 units of 100 ns
(1 ms), yet these actual waits clustered around 15 ms. Querying timer resolution
is therefore not a substitute for measuring the wait API used by a workload.
These are observed timings on this host and runtime, not guaranteed values for
every Windows installation.

The same executable and DB DLL, with only the runtime replaced by the delivered
combined907 DLL, reproduced the effect: DB yield medians were 15.0907 ms for a
1-us request, 15.1202 ms for 2 us, and 15.0700 ms for 1,000 us. Direct `select`
medians for actual 1/2/3-us waits were 15.0319/15.0867/15.0817 ms. The zero-yield
median remained 0.0001 ms. That second run also completed with native raw exit
zero and full observed process coverage.

## Source and binary path

The unchanged locker performs three `__os_yield(env, 0, rand() % 3)` calls per
iteration, for 2,000 iterations. A zero request calls `pthread_yield`; a nonzero
request goes through DB's `__os_sleep`, which adds one microsecond and calls
`select(0, NULL, NULL, NULL, &timeout)`.

The runtime converts that request into a relative `NtSetTimer` interval on an
ordinary notification timer and waits through `WaitForMultipleObjects`.
The receipt-bound D70 and combined907 `select.cc` files are byte-identical:
`d3b9f3046e3aa9f0103fb9d91191fbcb331165b3acd96d3ca4b1fdc22d2a87de`.
The independent same-binary combined907 measurement, rather than source equality
alone, establishes that this wait characteristic also occurs with that runtime.

Approximately two thirds of the random locker yields request a nonzero sleep.
The measured cost predicts about 60 seconds per locker just for these deliberate
yields, before self-blocking, wakeup-thread yields, scheduling and mutex backoff.
The non-hybrid DB TAS implementation additionally backs off from 1 ms up to
25 ms. The single wakeup thread also yields once for each released sleeper.
For sixteen lockers and 2,000 iterations, the measured yield distribution
predicts approximately 323 seconds of serialized wakeup-thread delay alone;
the observed corresponding cases took approximately 331-338 seconds. The
100-second small cases and larger-case scaling are therefore consistent with
the independently measured wait mechanism, not merely with a generous timeout.

The actual DB ARM64 lock/unlock binary contains exclusive-load/store operations
and `dsb sy` barriers. Presence of those instructions is useful evidence, not a
proof of all possible memory-ordering behavior.

## Implication for other consumers

A component polling or sleeping at microsecond granularity through this runtime
can spend tens of milliseconds in each wait despite requesting a much shorter
delay. Repeated waits can look like a hang or exhaust a timeout while making
correct progress. Before attributing a similar stall to mutex correctness:

1. Measure the actual wait API without contention, including a zero-wait control.
2. Record per-case progress, CPU time and wait states rather than infer progress
   from buffered output or overall host CPU utilization.
3. Keep the original failure and workload. A longer bound is diagnostic, not a
   pass criterion by itself.
4. If progress stops, capture the affected owned threads and wait chains; do not
   dismiss a possible ordering or alignment fault because timer cost is high.

No runtime timer, mutex implementation, machine setting, or workload reduction
is proposed by this investigation.

## Reproduction and retained evidence

Use the existing `db_channel_checks.py` receipt-verifying entrypoint with the
same sealed D70 driver and `--mode mutex --runs 1 --approved-mutex-matrix
--matrix-timeout 7200`. The historical default of 900 remains available for
reproducing the original budget failure; it is insufficient for this full
workload on the measured host.

`db_mutex_timing.py --run RUN_ROOT --output REPORT` requires an actual successful
full matrix and complete native exit coverage. It matches each driver PID and
creation FILETIME to its raw exit; it rejects missing cases, recycled PIDs,
nonzero exits and timed-out or partial runs.

The original 900-second receipt is never rewritten. The follow-up full-run
receipt SHA is
`805143b08af0912ac6ff5701141763f26df8ec48364df0a4960e58ee7750bc2b`;
the per-case result SHA is
`5814938099e82dae747199d26fc65629016817a00813422e9c7152cf5eaa39d7`.
The complete matrix ran on D70. The separate same-binary timing probe also ran
on combined907; that is not a combined907 full-matrix or full-suite claim.

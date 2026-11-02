# Original terminal lifetime receipts (0.9.9)

`studio_exec_command`, `studio_write_stdin` and terminal termination return
startedAt, observedAt, endedAt, elapsedMilliseconds, the original deadlineAt and
remainingLifetimeMilliseconds on the same run-owned process handle. Both pipes
and PTYs use the same measurement. Session terminal items and the tool display
show the same observed values; no extra shell command is needed.

The host records its monotonic timestamp and UTC display anchor immediately
before invoking the subprocess, after sandbox/cwd/PTY preparation. This measures
host-observed spawn-invocation-to-observed-exit lifetime, including spawn latency
and any real termination grace; it is not CPU time or exact kernel execution
time. Original boot ID, PID/birth observation and monotonic start/deadline/end
are saved on the durable process item. Nanosecond counters use decimal strings,
avoiding JSON/JavaScript rounding. Process IDs and ownership rules are unchanged.

The watchdog uses that one original absolute monotonic deadline. The existing
timeout_ms budget/default/maximum, termination grace, output limits, exit code,
signal and timeout reason remain unchanged. Polling or input never resets the
start or deadline and cannot extend the budget. Wallclock timestamps are display
anchors; elapsed and remaining time use the original monotonic clock/boot.

The first confirmed observation of process exit freezes duration before output
drain/cleanup. Later polling and the bounded in-memory handle cache cannot make
that duration grow. A retained terminal item returns its saved final measurement
without arithmetic against the current host boot. A lost end clock remains
unknown rather than being reconstructed at a later read.

Old/incomplete/missing timing receipts explicitly return null fields and
coverage=unavailable. No durations are inferred from file mtimes, creation dates
or foreign boots, and no historical records are backfilled. An unbounded or
unknown budget has no invented deadline. Timing coverage does not change whether
output, exit or cleanup was actually confirmed. Already frozen workers keep their
original code; the next authorized worker uses this release.

This is an additive result/item contract: every previous dynamic tool declaration
and argument schema remains byte-for-byte equivalent. Runtime guidance applies
to authorized project and skill sessions without replacing their frozen prompts.
No tests, fixtures, inference or user app/VM runs were performed; positive live
process/poll/final-duration acceptance remains open pending actual evidence.

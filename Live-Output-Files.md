# Live registered output files (0.8.40)

New execution workers refresh configured outputFiles while the original process
is running. They read only the already registered uppercase 8.3 names inside the
verified rebound deployment, with the original project/session/worker, VM lease,
boot and process generation. Existing settings validation, eight-file/64 KiB
bounds and private SFTP scope apply; no arbitrary guest path or shell is added.

Each observation has an eight-second read budget and at least five seconds
between completed rounds. Two bounded copies per file must agree before an
observed-stable receipt is published. Missing, changing, unreadable or over-budget
files stay unconfirmed. This is an observed interval, not a frozen live guest
filesystem. Identical bytes/name/boot/process/deployment reuse the immutable
receipt. New observations retain time and binding separately; old receipts are
never rewritten. Every normal status poll evaluates all criteria using the
latest saved file observations, rather than dropping them on polls without new
files. The browser and agent job results expose current findings and check time.

Stop takes priority; observations do not close a process or grant input rights.
The existing explicit completion request forces fresh file reads and the full
criteria preflight before authorizing a close, then rechecks final criteria and
owned cleanup. An expected exit code still needs an actual application exit.
File/image receipts or passed individual criteria do not imply a completed job.
A natural exit proceeds through the original final collection and cleanup; a
second live completion is rejected. Native console/exit gaps remain separate.

Current runtime guidance explains this behavior without changing persisted tool
declarations, old frozen prompts or worker releases. Older running workers keep
their original behavior; absent liveFileObservation does not claim live support.

Three focused cases extend existing observation checks: stable/deduplicated,
missing/later/changing files; rate limit plus forced preflight/exit/Stop; foreign
boot/process/deployment/path. Existing criteria cases, Python AST, build,
TypeScript and lint passed. All guest reads were isolated substitutes; no user
VM/job was replayed, launched, stopped or captured. Evidence:
Research/R4OS/Roadmap-Implementation/0.8.40/ in the development workspace.

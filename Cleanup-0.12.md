# Studio cleanup 0.12.X

Root services and direct workspace paths are the operating model.

## 0.12.3

Terminal stop, timeout, output limits and run cleanup retire the original process group with bounded, PID-bound TERM/KILL signals. PTY commands retain one session identity and completed handles report cleanup confirmation.

# Managed REA analysis programs

REA installations use an immutable private runtime below `Data/Skills/<skill UUID>/Runtimes/<source commit>/<recipe identity>`. The complete original 234-tool catalogue stays available. The runtime does not install agent plugins, modify system packages or enter project VMs.

The managed recipe backports REA's Linux kernel-thread detection to the pinned REA 6.8.0 source `d7df9df3393f`. The ownership sweep uses the kernel's `PF_KTHREAD` flag from the same process generation before and after the token read. A confirmed unrelated kernel thread is excluded from cleanup failures. The patch hash participates in the runtime identity. [REA upstream fix](https://github.com/morluto/rea/commit/5bb6591d58840d1cf07874729d5870cbb5723a7f)

The versioned recipe in `shared/rea-programs.json` records official release origins, archive sizes and SHA-256 values. It installs Ghidra 12.2 with full Temurin JDK25, pinned JADX metadata bridge, Apktool, Rizin, WABT, pwndbg portable, Binwalk from its locked original submodule, Wakaru, the matching native Frida Node binding, and private Python analysis packages. Chromium uses the exact Playwright revision from REA's dependency lock. Third-party notices and package licenses remain in their original trees.

Linux packages are downloaded against authenticated Debian repository metadata into a private empty package database. Archives are extracted into the skill runtime without maintainer scripts, global dpkg changes, service starts or device permissions. Source compilation runs without networking. Python installation allows wheels only; frida-tools' verified source is built offline before wheel installation. Build logs and receipts belong to the original source request.

`Readiness.json` preserves the actual native `binary_session` response, its grouped per-operation availability and complete catalogue count. A target-required operation is not an installation failure. Commercial providers, platform-specific targets, browser/agent client capabilities, and caller-authorised devices remain explicit prerequisites. General `doctor healthy=false` does not disable independent analyses. REA's native errors and evidence remain intact.

Each runtime exposes only its own controlled program paths and environment to the session namespace. Java/Ghidra can use its private loopback. Namespace root is mapped to the ordinary service UID; all capability sets are discarded before REA starts. Project access follows the accepted run's normal file and execution permissions.

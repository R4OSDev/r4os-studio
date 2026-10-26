---
name: r4os-update-packages
description: Plan, build, transfer, install, verify and recover R4OS update packages in Studio project sessions using bounded host tools and exact native evidence.
---

# R4OS update packages

Use this skill when a user requests an R4OS update package, persistent update installation or recovery. Read [the reviewed English workflow](references/Updates.txt) and [the source binding](references/source-profile.json) before acting.

This is project-session knowledge. Skill Manager sessions may edit the skill; they have no VM update tools. An active skill grants no permissions. If this session lacks the v5 update tools, create a new project session; preserve the old conversation. Never replace missing tools with SSH, network access, credentials or a guest shell.

Follow build artifact → immutable plan → R4UPack package → assigned VM readiness → own Inbox upload/full readback → public VERIFY → STAGE → actual live proof or own awaiting-commit batch → separately authorized COMMIT/reboot → correlated status/inventory/full hashes. Use the Studio tools and wait for their original durable jobs, without model polling or resubmitting writes.

Package version, native component version and target OS release are distinct. Preserve the actual project SDK/contract/compiler pins and catalogue target. Do not infer minimum dependency versions from API imports. Public VERIFY checks the actual installed state; there is no public JSON or VERIFY-BATCH interface. A valid package build does not imply native compatibility.

STAGE can execute live APPLY. COMMIT and a prepared RESUME-BATCH can install and reboot. Reboot/rollback need a concrete user task and their separate frozen session rights; commit and rollback default off. A rejected or unconfirmed effect is never permission to repeat a native write.

Read existing updates/jobs to resume a conversation. Preserve original package/VM/batch/transaction IDs and receipts. Never adopt a foreign or uncorrelated batch, overwrite Inbox paths, edit native private journals, stages, locks, backups, MODULES.JSON or VERSION.R4S. source=- alone proves no ownership. Studio leases do not atomically exclude another native administrator; the native API has no expected-batch argument.

A rolled_back journal with a rolling-back batch can require a separately authorized batch resume to finalize. This is a mutation, not a read-only probe. Confirm rollback as its own outcome, never installation success. Keep transport until terminal proof; cleanup removes only complete matching own package bytes. Stop does not undo a durable native installation.

Some guests reject SDK default /SOFTWARE targets and cannot atomically create a missing long target filename. Use an explicit supported source-manifest target and an already installed application where required, then rebuild. Studio never guesses a prefix or bootstraps a missing target.

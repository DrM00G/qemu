# Reusable sealed generation and future corruption evidence — design only

No new generation corruption or random sweep occurs in Phase10M. The approved
ELF now resides on verified FSW, so future faults to its actual filesystem/code
can affect path lookup, exec, loader reads and later demand faults. OS library
and required-data faults likewise pass through real on-demand verity/FEC.
Unused OS data can remain unread in operational mode. Keep the current observer's
own accesses (Python ELF/hash, filesystem listings, FSW block zero, libc and
mount/status queries) in the declared workload; probes are not observationally
free and may touch a purportedly unused target.

Use fresh exclusively owned QCOW2 children of one accepted immutable generation.
Retain the Phase10L injector guard design: regular files only, explicit backing
chain/content identity, bounded partition/file extents, exact seeded placement
list/units/counts/percentages, before/after hashes, closed writers before boot,
and no physical devices or writable golden/metadata sources. Case acceptance
does not regenerate any tree, parity, root or expected digest after corruption.

Cold boot means a new QEMU/Linux instance with damage present before its first
storage accesses. A post-clean-boot VM snapshot preserves code, page cache and
other memory; resumed operation under changed storage is a separate warm/resume
experiment. It cannot prove cold-boot survival. Record boot condition, injection
time, guest/host cache policy and QEMU CPU clock domain. Do not flush or preload
arbitrary files without declaring those accesses as part of the experiment.

## Required multidimensional evidence

Retain PASS, FAIL, NOT_REACHED, NOT_EXERCISED and UNKNOWN per axis, with raw
messages, timestamps and error reasons. A run can boot successfully yet fail
one FSW function; that is not the same as root failure or full application success.

| Axis | Evidence required |
|---|---|
| Kernel/initramfs/root | Process/console milestones, pinned effective boot chain, mapper construction, actual verified lower identity/options |
| Userspace/readiness | PID1, target/jobs/services and verified mounts/status/root/FEC, time of first valid and stable readiness |
| FSW filesystem | Correct verified read-only /opt/fsw, path/inode access errors, no raw mount or RAM substitute |
| Direct exec/loader | Absolute command, uid, syscall/errno or loader output, child exe/maps proof when available; no prehash requirement |
| Tasks/functions | Exact initialization/start order, sampling, packet receipt/route/queue/buffer, function-specific dependencies and outputs |
| Files/libraries/drivers | Declared accessed files and probes, actual EIO/errno/mapping errors, driver binding and fixture availability |
| Process lifetime | Exit/signal/timeout/forced kill, thread/process failure scope, normal or failed shutdown |
| Provenance/damage | Generation and manifest digests, precise damage/readback, original and child identities, clock domains, source/write audit |

Correctable requires observed FEC correction or another equally strong verified
recovery observation tied to declared fault locations, plus correct returned
data or required function output. A valid mapper status or intended small fault
is insufficient. Corrected data can remain damaged in the raw backing image;
keep raw and verified observations distinct.

Unrecoverable accessed damage requires a failed verified read/exec/mount with
adequate mapping/root/FEC and target evidence, not merely a slow boot, missing
message or absent peripheral. Metadata/root activation failures are separate
from a data-page EIO after launch. Retain timeouts as timeouts and missing
evidence as UNKNOWN rather than manufacturing a definite diagnosis.

Uncorrectable but unaccessed damage needs a separate duplicate-overlay diagnostic
that demonstrates unrecoverability, plus an explicit basis/limit for the primary
workload's accessed set. Reading the damaged target in the primary run changes
that condition. Likewise an entire-ELF in-guest hash forces early accesses and
must not be silently added to direct-launch survivability tests.

Partially functional means the evidence vector retains successful boot/services
and named functions alongside failed ones. The workload, observation duration
and clean baseline expectation must be explicit. After an unhandled process-wide
fault, do not claim its remaining threads are independently alive. Full
application success is only for all exercised required functions, never for
unimplemented/untested hardware or absent external fixtures. Existing SPI,
watchdog and serial limitations stay baseline conditions unless a measured
corruption effect changes them.

Begin future work with deterministic clean, correctable, required-code/data and
unused-data controls on matched generation children. Validate a guarded injector
before any hundreds/thousands-case batch. No implementation or authorization for
that sweep is supplied by this document.

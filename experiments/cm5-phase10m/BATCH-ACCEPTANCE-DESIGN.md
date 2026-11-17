# Future batch acceptance and readiness — proposal only

Phase10M implements persistent FSW and reuses one sealed generation; it retains
the existing per-run full content checks, BOOT selection and readiness spacing.
The following is not an implemented hash cache, relaxed assertion or new host
filesystem configuration.

## Per-generation acceptance

Intentionally stage/seal once per version. Accept original golden/OS identity,
actual layout, immutable image SHA256, installed ELF and its dependencies,
FSW tree/FEC/root, unchanged OS tree/FEC/root, effective initramfs, original
kernel/config/DT/BOOT identities, tool/source versions and full clean verification.
Retain strict assurance evidence separately from operational behavior. Bind a
clean direct-launch receipt and expected function metrics to the exact manifest
digest. Freeze outputs; never update metadata to agree with a damaged case.

A future batch controller can prepare verified kernel/initramfs exports once,
hold read-only descriptors and a generation lease, and create disposable children
for many cases. Its lease must bind inode/device/size, content digests, backing
graph, effective config and allowed case fault ranges. Unknown changes invalidate
the lease and all dependent results until reacceptance. Preserve startup and
end-of-batch digest attestations and each case's generation/lease identity.

Permission bits and stat/mtime checks are useful mutation detectors, not
cryptographic immutability. Never replace full content checks solely with them.
For stronger safe reuse, investigate supported host regular-file fs-verity or
another cryptographically enforced read-only snapshot/object mechanism, with an
explicit trusted-host/threat model and measurement of capabilities. Do not enable
it or manipulate host devices as part of this phase. Without a justified immutable
source mechanism, retain full checks; amortization is only a proposal.

## Per-case acceptance

Require an explicit accepted manifest digest, validate the generation lease and
all effective launch identities, exclusively create the new child, check its
regular-file ownership and exact backing graph, and record injection plan/readback
and cold-boot settings. Check source changes before launch and after exit. Retain
the unchanged original golden reference, case image identity, active overlay
allocations, guest writes, outcomes and receipt. Never silently reseal, substitute
an intact RAM ELF or accept arbitrary changed kernel/initramfs artifacts.

BOOT caching must respect the fault model. Data-only OS/FSW campaigns may reuse
exports only when the controller proves that BOOT dependencies are unchanged in
the actual child and immutable source. BOOT/partition-table/config faults must
execute selection from the damaged child; cached pristine exports would bypass
the test. An allowlisted injector alone is not proof if other sources/writers are
uncontrolled. A validated whole BOOT-range comparison or a precise audited
overlay-change model can support the data-only case; do not merely assume it.

Even cached artifacts must keep distinct original BOOT acceptance and effective
lab initramfs/root-policy identities. Phase10M's image has unchanged original
BOOT plus an explicitly substituted sealed-root initramfs; caching must not
erase this dependency.

## Readiness measurement

Phase10L measured roughly 134 host seconds from systemd entry to validated
readiness. The current observer runs every 30 seconds and requires two active
samples at least 20 guest seconds apart; service startup and sampling both
contribute. This phase leaves that contract unchanged to isolate persistent FSW.

A future profile could poll or subscribe to systemd state promptly (for example
bounded `systemctl` queries or authenticated service state notifications), then
check actual verified mounts, both V statuses, exact roots/FEC tables, PID1,
required target/job completion and required libraries immediately. Distinguish
active target from all required services being usable. Keep per-command and
overall deadlines, explicit failed jobs and missing mounts. Require a documented
stability interval or repeated independent checks appropriate to the experiment;
do not quietly remove the existing spacing and call it the same readiness test.
Record time of first valid readiness and time of stability confirmation separately.
Changing this contract deserves its own before/after clean and negative tests.

Priority after persistent FSW is measured control-path/acceptance amortization,
then evidence-based readiness improvements. No boot-scan reintroduction, verity
relaxation or QEMU UART fidelity claim is implied by faster host scheduling.

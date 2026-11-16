# Phase 10D — captured 6.18.50 recovery matrix complete

Local AI-assisted experiments only, not for upstream submission. Branch
`cm5-rp1-hardware`, HEAD `1a6703a4bb1590aa98e6993474b0a0551d8d8f60` remain
unchanged. No commit, push, reset, clean, stash, golden write, physical block
operation, EEPROM change or original input modification occurred. All prior
uncommitted sources and evidence were preserved. The sole earlier experiment
source extended here is Phase 10C `run.py`, through an opt-in recovery-case hook.
No QEMU hardware implementation changed in this phase.

## Recovery outcomes

| Case | Outcome | Actual evidence |
| --- | --- | --- |
| CLEAN | PASS_CLEAN | both roots2/V, direct verified digest, systemd and multi-user twice, LOGS persistence, normal exit |
| OS0 | PASS_RECOVERED | raw damaged, direct mapper digest equals golden, actual kernel FEC correction, both V, complete functional survival |
| OS-FAR | PASS_RECOVERED in two independent overlays | correction during original full scan before root mount, direct target digest, both V, complete functional survival |
| FSW0 | PASS_RECOVERED | explicit damaged raw p5 versus golden mapper digest, kernel correction, both V, complete functional survival |
| NO-FEC | EXPECTED_VERITY_REJECTION | separate labeled diagnostic hook, OS EIO/C, FSW roots2/V, explicit root refusal, normal poweroff |

The original physical kernel and original initramfs are used by all successful
root/userspace profiles. The inherited Phase 10C `result.json` fields
`multi_user` and `full_scan_complete` are console-marker-only and may be false.
`recovery-result.json` uses the saved independent userspace queries instead.
Full-scan completion follows the unchanged hook's root-handoff gate; it is not
a claimed per-byte trace of all 10 GiB. The no-FEC negative control uses the same kernel/module
and metadata but a **separate modified diagnostic initramfs**. It does not boot
userspace and is never called an original-production or recovered boot.


## Accepted evidence and measured milestones

Aggregate: `artifacts/report-final/result.json` (PASS), normalized individual
records and `comparison.json`. Exact runs are `d-clean-02`, `d-os0-01`,
`d-os-far-02`, `d-fsw0-01` and `d-no-fec-02`. The first independently recovered
OS-FAR plus its separately corrected evaluation remain additional evidence.
No accepted whole-guest run timed out; every QEMU process exited0.

| Case | Verified OS mount, guest s | Active multi-user queries, guest s | FEC messages | Wall s |
| --- | ---: | --- | ---: | ---: |
| clean | 252.684074 | 363.54, 394.66 | 0 | 396.54 |
| os0 | 232.661294 | 342.7, 373.67 | 10 | 376.65 |
| os-far | 252.019488 | 362.73, 393.68 | 7 | 395.12 |
| fsw0 | 248.446685 | 359.65, 390.54 | 10 | 392.86 |
| no-fec | not attempted | not attempted | 0 | 16.62 |

Wall values include final identity checking, and are not correction latency,
a controlled performance comparison or physical boot-time equivalence. FEC
messages can repeatedly correct the same one injected block; message totals
are not independent faults. Corrected raw blocks remain damaged after shutdown.
The no-FEC row is a rejecting diagnostic, not a recovered userspace boot.

## Inputs and provenance

All six input identities matched Phase 10C before the campaign. Every completed
run records and compares the full original inputs before/after guest execution:

- Golden regular file: 15,634,268,160 bytes, SHA-256
  `e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.
- Captured `kernel_2712.img`, SHA-256
  `154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d`.
- Original `initramfs_2712-osverified-v8`, SHA-256
  `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`.
- Original FEC-capable module within it, SHA-256
  `b1dca4c7c70d2df4ae778e7e1cde90471336ba494aa606fe574a909b2ebc4e37`.
- Captured DTB/config/cmdline hashes also remain in every `inputs-before.json`.
  These are not silently treated as QEMU's runtime generated DT or firmware reads.

Each run records QEMU executable identity, exact command, overlay/backing chain,
partition offsets, deliberate sectors/bytes, pre/post raw digests, pre-guest
allocation extents, userspace observations, FEC events, timeout and process status.
Whole-file overlay identity is taken after exit. Private assets/exports stay
outside the public checkout. The first CLEAN run predates adding a separate
harness-source hash record; executable/private input hashes are recorded there.
Subsequent physical runs include `harness-sources.json`.

## What proves correction

Faults replace one entire 4096-byte block with byte 0x5a, before QEMU starts on a
fresh overlay. The raw damaged-block digest is always
`f302957da5220938a7e3e51a8718c79b9e00dc13ab2119e8cfc978f041720382`.
The guest reads that raw partition block, then reads the same target from its
verity mapper using aligned `O_DIRECT`/`preadv`. This bypasses block page caches.
The mapper must return golden while raw remains damaged, and the actual captured
kernel must report FEC correction for the corresponding device/interleaver base.
No correction is inferred from module loading, metadata presence or boot alone.
The observer receives only target role/partition/block geometry; reference data
and expected digests remain host-side and are not supplied as a guest result.

| Target | Partition / data block | Absolute guest bytes | Original verified SHA-256 |
| --- | --- | ---: | --- |
| OS0 | p2 / 0 | 545259520 | 6401fa045488cc773681916e0de59b876b49dbe8eaa4db59ed0e78ecdc2bbc15 |
| OS-FAR | p2 / 262144 | 1619001344 | bfbedfa33f2237c259b4887fd9d299deb72fe8438a5f5438865874523310d69d |
| FSW0 | p5 / 0 | 11283726336 | 3767f788fc318481cc354ee1cf7cd343e4e0610c69f7c29bb58b7e5f024672db |

The intact original forty-chunk full 10 GiB OS scan precedes root mounting in
all successful original profiles. OS-FAR's first run reports target-consistent
correction at guest times 32.970894 and 33.156789, before verified root mounts at
251.369295. This independently establishes a pre-root target read, rather than
assuming coverage from block position or a later successful boot. Explicit
post-root direct reads additionally return the expected digest.

### Correct interpretation of the kernel FEC log

The numeric field after `FEC` is interleaved `rsb`, not absolute data bytes.
The [pinned official 6.18.50 algorithm](https://raw.githubusercontent.com/raspberrypi/linux/cff533aec2fa601846766b32ff57204e0a61bed7/drivers/md/dm-verity-fec.c)
computes rounds from protected blocks and RS data symbols. For captured OS
roots2, rounds=ceil(2642083/253)=10444; block 262144 corresponds to
`(262144 % 10444)*4096 = 4276224`. Different blocks can share this base, so a
log alone cannot uniquely identify a physical block. Controlled single-fault
provenance and the explicit raw/mapper target reads supply that identification.

Pinned source SHA-256 is
`5692aa9c5f0312abfbd62df95010400c22a26657e47602e0407c9a27f92f0ad9`.
The captured existing module's `verity_fec_decode` disassembly contains the
matching division/remainder operations at 0x3b7c/0x3b80. Source and module exports
remain private under `~/cm5-v8-lab/phase10d/fec-source-01/`; derived provenance
is in `artifacts/fec-interpretation-01/`. Exact external-module source-build
provenance is not independently established; the captured executable and actual
RS-base observations corroborate this exercised behavior.

## Functional survival and write attribution

A recovered case requires both original roots2 tables and valid statuses,
verified OS and FSW ro/norecovery mounts, systemd PID 1 executable, independently
active multi-user observations at least 20 guest seconds apart, captured OS
Python/libc diagnostics, guest LOGS fsync/readback, normal shutdown and independent
post-exit LOGS file recovery with debugfs. No filesystem mounting/journal replay
is performed on the host. A failed individual query is retained and not accepted
as a valid observation. Captured p5 still contains only empty lost+found, so no
FSW executable or production application survival is claimed.

Harness-originated fault allocations are recorded before guest start. After
exit, the entire fault-containing QCOW2 cluster must have identical content,
and all other allocated extents must lie within p6 LOGS. Thus FEC returns
corrected data without healing the raw backing block. This is net content and
allocation evidence, not a per-write event audit or proof that no transient
same-value write occurred. The public diagnostic LOGS file is independently
recovered after normal shutdown; this is not physical power-loss safety.

## Separate negative control

`d-no-fec-02` removes only OS FEC CLI options in a separate diagnostic hook.
Original RECOVERY/loop setup, FSW roots2, OS hash tree, pinned root and captured
module remain. The hook replaces the production FEC assertion/scan/handoff with
an explicit block 0 read and table/status/error capture, then refuses root and
powers off. Kernel logs reject data block 0; explicit dd returns1 with EIO;
OS reports `verity C`, FSW reports `verity V`. No systemd is reached or claimed.
Archive unit checks verify that only this hook's content differs, while the
original captured initramfs stays byte-for-byte identical.

## Tests and retained incomplete attempts

- QEMU/tools and affected qtest targets: build PASS, no hardware source changes.
- Focused qtests: RP1 6 + cm5io/MDIO 4 + MIP 3 + SDHCI 6 = 19 PASS.
- Generic platform and PCI SDHCI checks: 2 PASS.
- Phase 10A: 24 unit tests +10 synthetic cases PASS; sources unchanged.
- Phase 10D: 8 unit tests PASS, including real synthetic QCOW2 injection,
  neighbors/backing preservation, source-archive comparison, strict outcome
  gates and the nontrivial interleaver-base regression.
- Phase 9 clean/OS0/OS1/FSW0 PASS; no-FEC EXPECTED_FAILURE. All five completed
  with unchanged golden; the 6.18.62 fallback remains intact.

`d-clean-01` stopped before QEMU launch: qemu-img dd count/skip semantics yielded
an empty block export. The harness now uses a bounded raw offset/size view;
real QCOW2 unit tests validate the fixed reader. The failed attempt is retained
and documented in `harness-setup-01`, never counted as a guest run.

`d-no-fec-01` had real kernel rejection but its hook markers were redirected to
the captured initramfs log. Its result remains INCONCLUSIVE. A fresh diagnostic
explicitly sends its markers to UART, and `d-no-fec-02` passes the negative gate.

`d-os-far-01` booted and passed all functional/persistence checks, but its first
evaluator wrongly expected the absolute 1 GiB offset in the FEC log. Its original
INCONCLUSIVE result remains. `d-os-far-rechecked-01` separately reevaluates that
same evidence with the source-backed RS-base calculation and passes all checks.
One early systemctl query timed out; it was not accepted. Later independent
active observations at 362.22 and 393.17 establish the required survival window.
The fresh `d-os-far-02` confirmation also passes directly with the corrected
matcher and a new overlay. No recheck is needed for that run.

## Limits and next work

See [LIMITATIONS.md](LIMITATIONS.md) for the physical-versus-virtual comparison
and [NATIVE-RP1-NEXT.md](NATIVE-RP1-NEXT.md) for source-inspected native readiness.
No native link, downstream routing, translation, RP1 attachment or MSI behavior
changed here. GPEX remains available. Broadcom link-up is not fabricated.

The schema accepts future root counts/distribution records; this runner tests
only the original captured roots2 single-block cases and diagnostic OS-roots0.
No other metadata configuration, burst distribution or reliability rate is
established. Next: independently approved matching metadata for any new roots,
additional controlled distributions and longer survival workloads; then a
coherent native RP1 link/config/window/DMA/MIP slice with real Linux access.
No eMMC flash ECC/wear/radiation, physical repair time or secure-boot claim.
The physical 39.36-second logging interval remains unexplained as a measurement.

Exact commands: [README.md](README.md). Per-run results and aggregate JSON live
under ignored `artifacts/`; previous phases' evidence was not overwritten.

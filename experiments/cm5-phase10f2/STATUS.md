# Phase 10F.2 status — 2026-11-16

Local AI-assisted experiment, not for upstream contribution. Boot-source policy
and physical-reference DT subset are implemented and freshly validated. The
actual original-kernel guest, strict SPI and independent provenance gates pass. No physical EEPROM capture confirms `0xf14`; it remains an
**UNCONFIRMED fixture**, not a measured EEPROM value.

## Preservation and actual starting state

Branch `cm5-rp1-hardware`, HEAD `872181e1de29acb4c13ffdd8937ee6c9fa7d11bd`
exactly matched the supplied commit. No tracked/staged diff or untracked F.2
source existed. Untracked Phase8/9 artifact directories remain untouched.
Ignored F.2 evidence survived the crash, including `v8-policy-01`, its passing
strict native report/provenance, synthetic USB and fault results. These are
historical evidence, not fresh test counts. Missing README/STATUS/handoff are
now supplied. No reset, pull, stash, clean, checkout, commit, amend or push.

Private source-only checkpoint: `/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z`.
It stores initial status/diffs, 167 source paths with exact
`source-hashes.json`, and resume note.
No images, captures, secrets or build/evidence directories were copied.
Fresh ignored evidence: `/home/aweso/projects/qemu/experiments/cm5-phase10f2/artifacts/session1-20261116T114011Z`.

The accepted 15,634,268,160-byte golden image exists at
`/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img`, with established SHA256
`e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.
Preflight used exact device/inode/size/mtime continuity against saved accepted
identity; all five physical boot assets received fresh SHA256 checks. The
existing reader/runner additionally performs full backing identity hashes per
its existing selection/prelaunch/preservation gates. No golden copy was made.
See `input-preflight.json` for precisely what was checked. Existing 10F.1
accepted manifest and native-SPI baseline remain available; no acceptance was
derived from faulted media.

## Implementation and bounded policy coverage

Only experiment code changed. Policy improvements reject missing acceptance
before disk reads, avoid probing an unavailable unselected pathname through
`samefile`, and reject an active source reused in the selected backing chain.
Hardlinks, same path, source-specific missing images, real QEMU block EIO,
wrong/stale manifests, changed selected bytes, malformed layout/config,
unused-file mutation and budgets 0/1/3 have bounded tests. Only explicitly
operator-declared absence falls through; any present-source failure stops.
The shared selector already rejected missing manifests later; this is earlier
validation, not a newly invented integrity requirement.

DT ctypes signatures, borrowed-pointer lifetime, returned lengths, property
update limits, checked node names and library header checks are explicit.
The full Python DT structural validator runs before C access. Source hashes are
verified before libfdt compilation; accepted binary hashes are enforced for
libfdt/dtc/fdtoverlay. Duplicate external/local fixup locations, malformed local
fixup encodings and offsets fail closed. No ad hoc binary DT edits or new
peripheral registers were added.

The guest observer now hashes every runtime DT node's properties and records
bounded semantic compatible/status declarations. `runtime_compat.py` compares
those actual declarations against the selected physical reference. Its tested
minimal `nospi10` slice validates physical SPI10 absence and preserves enabled
independent native RP1 SPI0. It is explicitly a no-change substitution.

## Fresh tests and evidence levels

| Gate | Outcome / evidence |
| --- | --- |
| QEMU + four hardware qtest targets, -j2 | PASS; build already current |
| Pinned libfdt tooling | PASS; two existing const-qualifier warnings |
| F.2 final host units | 47 PASS, `units-final-06.log` |
| F.1 / F / A host units | 23 / 20 / 24 PASS |
| D / strict E host units | 8 / 3 PASS |
| A synthetic proxy matrix | 10 PASS, header-only proxy evidence |
| RP1 / CM5IO / MIP / SDHCI qtests | 7 / 7 / 3 / 6 PASS |
| USB-first distinct payload execution | PASS, synthetic guest only |
| Actual runner no-launch MBR + selected-digest negatives | 2 PASS, synthetic media |
| Physical-reference transformations | PASS subset, full config unsupported |
| Actual original-kernel V8 guest | PASS; independent 14-check SPI and 16-check provenance |
| Targeted 6.18.62/GPEX control | PASS; clean surrogate, golden unchanged |

The initial SDHCI run aborted because `CM5_PHASE8_IMAGE_DIR` was omitted; the
fresh private-directory retry passed all six. This host permits the Unix socket
qtests; earlier F.1 sandbox denial no longer applies. Initial ctypes testing
requested unavailable `fdt_check_full`; pinned-library-compatible header checks
plus the existing full structure validator fixed that API mismatch. Early
failed local-fixup tests used a fixture whose hand-written metadata dtc removed;
the final fixture mutates compiler-generated local fixups and passes. All failed
logs remain, without being counted as final passes.

## Device Tree evidence and compatibility boundary

Fresh `reference_audit.py` reads accepted selected physical DT, actual map and
resolved overlays through a fresh locked read-only QCOW2. Its ledger is private
under `physical-reference/`. `dwc2,dr_mode=host` produces status okay and dr_mode
host; `nospi10` disables `/soc@107c000000/spi@7d004000`. They are independent
transformations of the original reference, not a falsely complete firmware
pipeline that silently skips graphics. Normalized DTS diffs and source/parameter/
tool/output hashes are retained privately. Final-code rechecks reproduce both
output hashes in `physical-final-recheck.json`.

Graphics maps to `vc4-kms-v3d-pi5` but dormant fragment semantics stop it; audio
semantics are unestablished. The generated runtime tree is retained. Board source
`hw/arm/cm5io-dev.c` explicitly rejects supplied `-dtb`; physical USB, graphics
and SoC SPI10 lack compatible modeled peripherals. No runtime DT installation,
EEPROM execution, electrical USB enumeration, secure boot, tryboot, physical
retry timing or proprietary firmware-equivalence claim is made.

## Fresh captured V8 integration

Run: `artifacts/session1-20261116T114011Z/session1-20261116T114011Z-v8/`. Actual full command is
`v8-command.json` in the evidence root; selected private inputs, argv and source
snapshot are linked by `provenance/provenance.json`. USB is explicitly unavailable;
the source trace records no USB reads and selects eMMC. Kernel SHA256
`154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d` and
initramfs SHA256 `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`
are exact BOOT-selected bytes from this same disposable eMMC. The selected
physical DT is exported/validated but **not executed**.

Both original roots2 verity mappings report V, verified OS/FSW are mounted,
PID1 is original systemd, and multi-user is independently active at guest uptimes
365.04 and 395.9 seconds. Earlier inactive observations remain.
All 90 native SPI messages / 69,210 bytes have one CS segment per message at
10kHz; all 14 independent native PCIe/BAR/MSI-X/MIP/SPI checks pass. All 16
selected-byte/argv/runtime provenance checks pass. QEMU exits 0 without timeout,
normal poweroff is observed, and host post-shutdown LOGS readback matches guest
fsync/readback. `recovery-result.json` is PASS_CLEAN with all checks true.
Recorded run wall time is 411.12s; this is not physical timing.
Legacy serial-marker-only `multi_user` and `full_scan_complete` fields remain
False and False; they are not rewritten as passes.

Actual runtime generated DT SHA256 remains
`8f9ce2e6c3065b87b0b84e44f3c181192b94a4ee8c01d9352bde3952f13b0e34`.
`runtime-comparison.json` checks all five runtime observations against that
independently accepted identity. Its exact property-hash comparison identifies
315 physical-only nodes, 32 runtime-only nodes and eight changed common nodes.
Physical normalized diffs remain private; the runtime comparison contains hashes
and hardware declarations. No transformed physical tree was installed.

`input-preservation.json`, `LOGS-readback.json`, `boot-source-trace.json` and
`reason-taxonomy.json` provide concise independent artifact links and outcomes.
`physical-final-recheck.json` reproduces the fresh reference audit's output hashes
with the final fixup validation. Later bounded file-read validation changes are
covered by the final units. The guest's execution snapshot predates some later
negative-test/DT hardening; these do not change the exercised eMMC success path.

## Remaining design boundaries and next smallest patch

The requested bounded proxy and compatibility-audit work is complete. The
sequential surrogate control passed; final source/status accounting is below. Physical firmware behavior and installed runtime DT
transformations remain deliberately unsupported, with the exact compatibility
diff and tested absence slice delivered instead. A future installed transform
requires an explicit opt-in generator/loader contract, allowed modeled binding
paths and postconditions, followed by a genuine full guest gate. Keep the known
generated fallback.

Phase10G should add separately capped FIFO-drain/next-refill tracing for the
preserved 100kHz framing failure. The self-contained handoff supplies exact
previous failed message indices and trace requirements. Do not hold CS
indefinitely, relax the strict oracle, alter original drivers or repeat a broad
FEC campaign. No new high-rate SPI result or physical timing claim is made.

## Final accounting and handoff

The single targeted 6.18.62/GPEX clean control passed, powered off normally,
and verified golden identity unchanged. Its service failures/loop-device shutdown
messages remain in serial evidence; the unchanged control evaluator passes all
required checks. This surrogate result is separate from original-kernel evidence.
Fresh totals are 125 host unit tests, 23 hardware qtests, ten header-proxy cases,
one distinct USB-selected synthetic execution, two actual-runner no-launch
negatives, one full original V8/native-SPI integration and one surrogate control.

`evidence-index.json` links commands, results, private reference diffs and the
self-contained handoff. `source-manifest-v1.json` records final source hashes,
initial-checkpoint differences and actual execution-snapshot location. Final
Git status and unstaged/staged diffs are saved beside it; no changes are staged.
The original branch/HEAD and old Phase8/9 artifact directories remain. Original
input preservation passes. No commit, push or destructive Git action occurred.
All launched guests and block readers exited; no experiment guest/build/test is
intentionally left running. See process audit and NEXT-SESSION.md for continuation.

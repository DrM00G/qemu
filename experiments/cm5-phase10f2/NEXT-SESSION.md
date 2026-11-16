# Independent continuation: Phase 10F.2 / Phase 10G

This is LOCAL AI-assisted experimental work, not upstream-eligible QEMU code.
Read repository AGENTS.md and docs/devel/code-provenance.rst first. No commit,
push, reset, clean, stash, destructive checkout/pull or original-media writes.
Never access physical block devices, EEPROM/OTP/RPMB or host raw disks. Preserve
old failed runs; every test/run/work directory must have a fresh unique name.
Use -j2 builds for host stability and only one full guest at a time.

## Exact source and evidence starting points

Repository `/home/aweso/projects/qemu`, branch `cm5-rp1-hardware`, HEAD
`872181e1de29acb4c13ffdd8937ee6c9fa7d11bd`. This session began with no tracked
changes and only untracked Phase8/9 artifact directories. Those remain.
No commit/push was made. Session edits are limited to experiment files:

- `cm5-phase10f1/runtime_observe.py`: actual runtime DT property inventory.
- `cm5-phase10f2/boot_policy.py`: earlier manifest check, alias/backing identity
  rejection and nonselected missing-path handling.
- `cm5-phase10f2/dt_pipeline.py`: explicit ctypes ABI/lifetime/length checks,
  pinned tool hashes and external/local fixup validation.
- `cm5-phase10f2/build-dt-tools.sh`: verify pinned C/header sources.
- `cm5-phase10f2/test_policy.py`, `test_dt.py`: expanded positive/negative tests.
- New F.2 `runtime_compat.py`, `test_runtime.py`, `toolchain.json`, README, STATUS
  and this handoff. Actual final Git status is in the fresh evidence directory.

No hardware model, qtest, kernel, driver, original initramfs, golden image or
accepted hash manifest was changed. Initial source-only checkpoint:
`/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z` (`source/`, `source-hashes.json`, status/diffs/resume note).
Fresh ignored evidence: `/home/aweso/projects/qemu/experiments/cm5-phase10f2/artifacts/session1-20261116T114011Z`.
Exact launch commands and regression commands are JSON there.
`evidence-index.json` links all results; `source-manifest-v1.json` gives final
source hashes and checkpoint differences. No experiment processes remain. The actual
selected guest execution source snapshot is in its private Phase10C directory;
some later negative-test/validation hardening occurred while it was running.
Do not describe the final source inventory as a prelaunch execution snapshot.

## Private inputs (paths only; keep raw bytes outside Git)

- Golden `/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img`,
  15,634,268,160 bytes, SHA256
  `e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.
- Original captures `/home/aweso/cm5-phase10-private/physical-boot/boot-assets/`,
  with `/home/aweso/cm5-phase10-private/physical-boot.sha256`.
- Accepted manifest `/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json`;
  its sibling inputs-before/baseline-policy/reference-read records establish
  independent pre-fault acceptance. Do not recreate acceptance from fault media.
- Original F.1 baseline `/home/aweso/cm5-v8-lab/phase10f1/accepted-20261114-02/`
  and repo `experiments/cm5-phase10f1/artifacts/v8-selected-20261114-02/` with
  native-report-20261114-01 and provenance-20261114-01.
- Fresh disposable eMMC `/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z/v8-emmc.qcow2`.
- Fresh physical-reference QCOW2 `/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z/reference.qcow2` and audit
  `/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z/physical-reference/` (raw DTs, normalized diffs and read ledger).
- Final-code transform rechecks `/home/aweso/cm5-v8-lab/phase10f2/session1-20261116T114011Z/final-dwc2/` and `final-nospi10/`.
- Fresh synthetic USB and runner-negatives media stay under this private root.
- Fresh full run private exports/command/source snapshots live at
  `/home/aweso/cm5-v8-lab/phase10c/session1-20261116T114011Z-v8/`.

Physical BOOT_ORDER remains **UNCONFIRMED**. `0xf14` is a proxy fixture only.
The proxy does not execute ROM/EEPROM or enumerate physical USB. Only declared
absence causes fallback. Present-media errors stop; no host-kernel fallback.
USB synthetic execution is a tiny ARM64 marker/PSCI program, not Linux, a real
USB controller workload or initramfs execution.

## Checks and limits

Fresh final F.2 host units: 47 PASS. F.1/F/A/D/E units: 23/20/24/8/3 PASS.
A synthetic matrix: ten cases PASS at header-only proxy level. RP1/CM5IO/MIP/
SDHCI qtests: 7/7/3/6 PASS. Build -j2 PASS and pinned libfdt build PASS (two old
const warnings). Synthetic USB-first distinct payload execution PASS. Two real
runner synthetic-media negatives stop without launch (MBR, selected digest).
Initial SDHCI abort was a missing CM5_PHASE8_IMAGE_DIR, fixed with fresh private
scratch directory. Socket qtests work on this host; old sandbox denial does not
apply. Retain early failed ctypes API/fixture tests as diagnostics.

Fresh original-kernel V8 gate: PASS, with 90/90 strict 10kHz CS messages, both
roots2/V mappings, original verified OS/FSW, systemd, active multi-user at
365.04 and 395.9 seconds, exit0 and persisted LOGS. All 14 independent SPI and
16 independent provenance checks pass. Runtime comparison passes all five
observations against the accepted generated-DT hash (315 physical-only, 32
runtime-only, eight changed common nodes). Sequential 6.18.62/GPEX clean surrogate: PASS, normal shutdown and golden
unchanged. Fresh aggregate totals: 125 host units, 23 hardware qtests.
Never count pending or historical results as fresh. Legacy multi_user/full_scan
serial-marker flags can be false despite genuine independent active multi-user
observations; report the independent observations and retain the raw flags.

## DT design decisions and smallest next patch

Physical dwc2 host and nospi10 effects are independently reproduced from exact
captured sources. Graphics dormant fragments/audio stay unsupported. They are
not a full firmware-ordered physical pipeline and were never installed.
Board code `hw/arm/cm5io-dev.c` rejects `-dtb`. Existing generated DT remains
compatible with the modeled native PCIe/RP1/SPI path; physical USB/graphics/SoC
SPI10 declarations are unsuitable. No new registers or unsupported devices were
invented. Runtime compatibility uses actual guest FDT hash plus all node/property
hashes, checked against the independent accepted generated-DT hash
`8f9ce2e6c3065b87b0b84e44f3c181192b94a4ee8c01d9352bde3952f13b0e34`.
The minimal nospi10 runtime slice validates absence and preserves RP1 SPI0; it is
an explicit no-change substitution, not an installed transformed DT.

Next DT patch: define an opt-in generator-side transformation contract for only
modeled bindings, with allowed property paths and postconditions, before allowing
any external DT input. Verify header SPI enable/slave declarations, native clock
phandles, interrupt parents and PCI ranges against actual QOM hardware. Preserve
the generated fallback and accepted runtime identity. An installed transform
requires a new full captured V8/native/strict-SPI gate, not just physical diff.
Do not inject physical nodes merely to make the trees look alike.

## High-priority Phase 10G SPI continuation

Read `experiments/cm5-phase10e/SPI-NEXT-CHECKPOINT.md` fully. Separate shifter/
FIFO accounting is already corrected. 10kHz framing passes; preserved 100kHz
result has 93 segments for 90 messages (splits at message indices 3,32,35).
All bytes correct does not pass strict CS framing. No new 1MHz test is justified.

The next smallest hardware experiment is a separately capped **drain / next
refill** trace: on completion with FIFO empty, and next DR write from idle,
record virtual timestamp, previous deadline, FIFO/shift/IRQ/SER/CS state. Record
timer-arm time before/after callbacks; correlate with strict message boundaries.
The old 256-event diagnostic ends before the first failed message. Do not infer
starvation from a timestamp spanning logging/CS callbacks alone. Keep the strict
oracle, original driver and low-rate control; never hold CS indefinitely or
hide fragmented messages. Add a deterministic trace qtest first, then at most
one bounded 100kHz diagnostic guest if the trace can capture the failing gap.
No broad peripheral rewrite, full FEC campaign or physical timing claims.

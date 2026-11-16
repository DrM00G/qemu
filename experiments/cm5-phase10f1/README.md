# Phase 10F.1: captured V8 selected from virtual BOOT

AI-assisted local experiment only, not eligible for upstream contribution under
`docs/devel/code-provenance.rst`. See STATUS.md for executed outcomes and exact
evidence paths. No EEPROM/boot-ROM instructions execute.

From `/home/aweso/projects/qemu`, choose new IDs for every invocation. Private
captured content, exports, manifests and expanded guest commands stay outside
the checkout. All disks below are disposable regular QCOW2 files backed by the
unchanged accepted golden image. Never run against physical storage.

```sh
# This environment disallows socket bind and socket introspection. The explicit
# pipe transport reads the same QCOW2 through a persistent read-only QEMU graph.
export CM5_BOOT_READER=qemu-io
export CM5_BOOT_PREFETCH=65536
python3 -m unittest discover -s experiments/cm5-phase10f1 -v
python3 -m unittest discover -s experiments/cm5-phase10f -v

# Independently verify captured identities and accepted golden, BEFORE faults.
python3 experiments/cm5-phase10f1/prepare.py \
 --work /home/aweso/cm5-v8-lab/phase10f1/accepted-repro01

python3 experiments/cm5-phase10c/run.py --control-pipes \
 --dma --batch --profile native --debug-shell --poweroff-after-validation \
 --recovery-case clean --native-rp1-test --native-spi-hz 10000 \
 --boot-selection-policy emmc-only --boot-config-profile cm5-headless-lab \
 --boot-overlay /home/aweso/cm5-v8-lab/phase10f1/accepted-repro01/emmc.qcow2 \
 --boot-expected /home/aweso/cm5-v8-lab/phase10f1/accepted-repro01/accepted-hashes.json \
 --timeout 600 --output experiments/cm5-phase10f1/artifacts/v8-repro01

python3 experiments/cm5-phase10e/report.py \
 --run experiments/cm5-phase10f1/artifacts/v8-repro01 \
 --output experiments/cm5-phase10f1/artifacts/v8-report-repro01

python3 experiments/cm5-phase10f1/evaluate.py \
 --run experiments/cm5-phase10f1/artifacts/v8-repro01 \
 --native-report experiments/cm5-phase10f1/artifacts/v8-report-repro01/result.json \
 --output experiments/cm5-phase10f1/artifacts/provenance-repro01

# Requires PASS for clean userspace, persistence and native SPI before faults.
python3 experiments/cm5-phase10f1/faults.py \
 --clean experiments/cm5-phase10f1/artifacts/v8-repro01 \
 --expected /home/aweso/cm5-v8-lab/phase10f1/accepted-repro01/accepted-hashes.json \
 --work /home/aweso/cm5-v8-lab/phase10f1/faults-repro01 \
 --output experiments/cm5-phase10f1/artifacts/faults-repro01

python3 experiments/cm5-phase10f/runner_smoke.py --control-pipes \
 --work /home/aweso/cm5-v8-lab/phase10f1/synthetic-repro01 \
 --output experiments/cm5-phase10f1/artifacts/synthetic-repro01
```

Omit the transport environment variables and `--control-pipes` on a host that
supports the established NBD/Unix-socket path. The transport is explicitly
chosen; a selection error never switches inputs or boots host capture files.
The qemu-io implementation validates hex dump addresses, lengths and successful
read counts, uses bounded replies/timeouts and propagates real block errors.
Optional 64KiB aligned prefetch uses a 2MiB LRU. The read ledger records actual
QEMU logical requests including prefetch, not cache-hit request sizes. This is
still not physical firmware/card read coverage. Default prefetch is disabled.

`--control-pipes` uses mode-0600 local FIFO chardevs for QMP and the existing
debug UART. It changes host control transport, not guest boot inputs. No host
network service, kernel NBD attachment or mount is required. Existing direct
host profiles and strict default Phase10F config handling remain available.
`--boot-overlay` now permits `--recovery-case clean`, which only observes the
existing clean persistence profile; faulted recovery cases remain forbidden.

## Validation contract

The original initramfs is never unpacked to host paths, repacked or modified.
The validator supports sequences of newc archives, zero padding, zstd frames
and gzip members. Every decoded compressed segment must contain complete newc
archives, with hex fields, names, payload bounds, alignment padding, checksums
and trailers checked. Compressed frame termination/checksum and all remaining
input are checked. Unknown compression, skippable zstd frames, dictionaries
without a supplied dictionary, nested compression, malformed/truncated data,
nonzero newc alignment padding, oversized windows and excessive expansion fail.

Stored input and cumulative decoded output each have a 128MiB bound; libzstd
uses a 64MiB maximum window, 64KiB streaming output chunks, and never allocates
from the frame's advertised decoded size. There are at most 128 archives,
262144 entries and 256 non-padding segments. Segment stored/decoded hashes and
an aggregate decoded-stream hash (including inter-archive zero padding) are
recorded. This is structural validation, not proof that arbitrary programs can
execute. Only the independent guest evidence demonstrates actual execution.

## CM5 headless policy and fidelity reductions

`cm5-headless-lab` explicitly declares a CM5 on the official I/O board. It does
not detect a board through firmware. Sources are Raspberry Pi documentation
revision `c6a64966af136da21a1e55551c5a395cb6987fce`, privately pinned at
`/home/aweso/cm5-v8-lab/phase10f1/reference-20261114-01/`, and the actual accepted
BOOT overlay README, flattened overlays and overlay map. The original BOOT
config is not copied into this source tree.

| Category | Supported operation |
| --- | --- |
| Interpreted | `[all]`, `[none]`, known model filters; both `[cm5]` and `[pi5]` match; other known model filters are inactive |
| Interpreted | Root-file textual includes, inherited filter state, last assignment, bounded depth/cycles/content/line lengths |
| Interpreted | Explicit kernel/initramfs/cmdline/DTB; followkernel or zero placement request; final auto-initramfs enable/disable; CM5 64-bit-only flag |
| Interpreted subset | CM5 default kernel_2712.img, kernel8.img fallback only when default is absent and no explicit kernel; default cmdline.txt; auto naming from kernel prefix |
| Known-board selection policy | Default bcm2712-rpi-cm5-cm5io.dtb; missing CM5 DTB stops, no physical Pi5-DTB fallback implemented |
| Lab substitution | QEMU ARM loader allocation replaces firmware followkernel placement |
| Lab substitution | `dtparam=audio=on`: no audio enablement in generated DT |
| Lab substitution | camera/display auto-detection: no attached lab devices or probing/automatic overlays |
| Lab substitution | vc4-kms-v3d: generated headless DT replaces graphics/CMA/audio operations; no overlay applied |
| Lab substitution | dwc2,dr_mode=host: USB host setup omitted; no supported USB workload |
| Lab substitution | nospi10: SoC SPI10 is absent from lab DT; separate RP1 SPI0 stays explicitly enabled for the established synthetic workload |
| Lab substitution | max_framebuffers=2, disable_fw_kms_setup=1, disable_overscan=1: no firmware framebuffer/KMS/overscan synthesis |
| Lab substitution | arm_boost=1: TCG/fixed lab clocks replace physical boost policy |
| Unsupported, fail closed | Every other active directive/value, unknown conditional, prefix, explicit address, unsupported overlay parameter or ambiguous explicit initramfs plus final auto_initramfs=1 |

Each active directive has an explicit private ledger outcome. Inactive ordinary
directives are recorded but not executed. Selected overlays' requested source
bytes are structurally checked and digest-gated. Firmware overlay application,
symbol fixups, parameter effects and overlay_map remapping are not executed.
The inspected map maps vc4-kms-v3d to vc4-kms-v3d-pi5 for BCM2712; this has been
audited privately rather than presented as an applied overlay. No physical
graphics/CMA/USB/audio effects are claimed from accepting those directives.

The selected physical DTB is validated, exported and hashed, but QEMU executes
its compatible generated lab DT. The selected original compressed kernel and
original initramfs are exported byte-for-byte and passed through `-kernel` and
`-initrd`; no pristine capture path is used after selection. Cmdline whitespace
normalization and console/debug additions are recorded separately. The in-RAM
observer hashes `/sys/firmware/fdt`, `/proc/cmdline` and chosen bootargs so the
effective runtime tree and command line can be compared with selected inputs.
This remains a software selection proxy and compatible loader, not physical
boot-ROM, EEPROM execution, secure boot, or complete hardware equivalence.

## Remaining firmware work

1. Extend the explicit profile only for evidenced selector operations (prefixes,
   additional filters, missing-default behavior), with bounded negative tests.
2. Implement a separately tested DT transformation pipeline: overlay map,
   symbol/local fixups, parameter ordering, input/output hashes and supported
   bindings. Retain the generated-DT fidelity label until then.
3. Model declared boot-source policy, retry/tryboot and recovery separately from
   guest verity/FEC outcomes. Do not infer these from proxy BOOT fault results.
4. Identify EEPROM image/version and documented ABI before considering actual
   firmware execution. Firmware authenticity needs its own trust model; lab
   digest acceptance is not a firmware signature check.
5. Retain native RP1/strict 10kHz hardware baseline; investigate higher-rate
   framing in its separate preserved workstream.

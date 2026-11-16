# Workday comparison plan — approval and read-only baseline

This is a plan, not an executed physical capture or authorization to operate
proprietary FSW. No FSW was obtained or explicitly launched in Phase10I; captured-image boot
services were not changed, and no approved application workload was tested. Ask the supervisor
which interfaces, device APIs, reset behavior and spacecraft simulators the
approved workload requires. Every capability-manifest entry currently marks
required_for_fsw UNKNOWN. In particular ask whether GPIO uses cdev/libgpiod,
legacy sysfs, /dev/gpiomem or direct MMIO; these are different requirements.
Ask about UART/I2C/SPI/DMA/network/USB/storage, interrupt expectations, external
stimulus/response and numerical/output acceptance criteria without assuming any
is needed. Obtain approval for data retention/redaction and the workload first.

## Environment and identity envelope

Use separate physical, qemu and linux-only environment tags and unique run IDs.
Record UTC start/end, monotonic clock name/origin, architecture, CPU count,
software/configuration hashes, fixture identity and operator-approved actions.
For QEMU include executable/source hashes, exact machine/clock/TCG profile,
selected BOOT hashes, generated/runtime DT identities and disposable image
identity. Fixed instruction time is an execution convention, not CPU cycles.
For physical capture identify the approved board/I/O revision and running kernel,
modules and runtime DT. Keep raw DT, journals, serial numbers, MACs, device IDs,
paths or credentials in approved private storage; publish only reviewed summaries.
Linux-only and CM5 builds may have different binary hashes: record source/build
identity, ABI and matched input/output contracts rather than claiming identical
binaries across architectures.

## Initial read-only observations, if approved

- Kernel release/version, loaded module names and hashes of approved kernel/module
  files; runtime /sys/firmware/fdt hash and a privately retained copy. Distinguish
  selected boot-file DT from firmware-transformed running DT. Do not change DT.
- Existing PCI hierarchy, vendor/device IDs, BAR resources, negotiated link state,
  driver symlinks and interrupt allocations. Prefer existing sysfs or read-only
  lspci output; never use setpci, BAR writes or arbitrary register scans.
- /proc/interrupts snapshots around a defined idle observation window, with the
  clock and window length recorded. Do not infer latency from counts alone.
- Existing /sys/bus platform/PCI/SPI/I2C/GPIO/MMC names and driver links; configured
  bus/device identities and DT dependencies. No i2cdetect, spidev transfer test,
  GPIO line request/toggle or broad raw-MMIO access belongs in a read-only baseline.
  A GPIO request can change direction or ownership even when called a read.
- Existing service/process identities, approved executable hashes and status.
  Avoid environment/command-line/FD-content dumps that may expose credentials or
  proprietary configuration. Supervisor-approved FD-type summaries may identify
  device dependencies without opening or exercising those devices.
- Existing mount/verity status, original roots2 configuration and persistent-log
  health, if permitted. Do not reseal, remount, repair, alter partitions or inject
  faults. Do not touch EEPROM/OTP/RPMB or physical block-device contents.
- Existing clock/provider summaries only if already available and approved.
  Do not load modules, mount debugfs, change rates or enable tracing as part of
  the baseline. Some register/debugfs reads have side effects or unsupported
  virtual paths; Phase10I's bounded GPIO model does not support bulk54-pin
  pinctrl debug dumps. Use its validated cdev test only inside disposable QEMU.

## Approved application comparison, a later stage

After the supervisor identifies and approves FSW/software, record build/config
hashes and an approved normal workload: inputs, command sequence, random seed,
initial persistent state, external simulator version and expected responses.
Run Linux-only, CM5-specific and private QEMU variants only where those interfaces
are supported and approved. Preserve all errors and first messages; compare
application outputs, counts/checksums, status and recovery criteria before timing.
Document any unavailable peripheral or substitute. Do not silently substitute a
synthetic loopback, VirtIO NIC or generic UART for required physical behavior.

GPIO20->21 and the SPI XOR0xa5 slave in this laboratory are synthetic fixtures;
matching physical wiring and response devices have not been established. Any
physical connection, device operation, additional tracing, logic-analyzer setup,
stress, reset or fault injection needs its own explicit approval. No production
boot/firmware, Windows power/driver, physical storage or verification changes are
part of this plan.

Record tracing/tool overhead and scheduling sensitivity. QEMU shifter/FIFO and
scheduler timestamps are internal diagnostics, often unavailable physically.
Keep QEMU virtual_ns, guest monotonic time, host time and analyzer time distinct;
never subtract across them without a documented synchronization experiment.
Unknown/unmeasured values stay null. Save comparison evidence under the approved
private retention policy and review it before sharing.

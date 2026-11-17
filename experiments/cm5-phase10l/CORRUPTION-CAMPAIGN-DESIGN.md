# Future storage corruption campaign — design, no sweep authorized

Use a fixed sealed generation and a fresh exclusively owned QCOW2 overlay for
each case. Keep strict recovery assurance and operational survivability as
separate experiment axes. Strict performs the exhaustive OS scan and may reject
otherwise unaccessed damage; operational preserves on-demand verity/FEC and
permits testing which required accesses and application functions still succeed.

## Reproducible case manifest

Each case must record:

- Case ID, seal-generation ID and full SHA256, logical image size, kernel/DT/
  initramfs/config/cmdline identities, original or derived acceptance-policy IDs,
  ELF/config/library inventory, QEMU binary/source/harness IDs and CPU timebase.
- Partition table digest; role/number/start/length; target data, hash-tree,
  metadata or FEC file, exact filesystem-to-image extent map if applicable.
- Fault seed, PRNG algorithm/version, placement algorithm, exact ordered fault
  list and its digest. Record random, contiguous, targeted-codeword and
  file-extent cases separately. A seed alone is not a reproducible placement.
- Count and units: attempted edits, distinct 512-byte sectors, distinct 4096-byte
  integrity data/hash blocks, actual changed bytes, bit flips and overlaps.
  Record offset coordinate system and both partition-relative and image-logical
  offsets. Never confuse QCOW2 container offsets with guest logical offsets.
- Pattern (e.g. fixed XOR mask or repeat byte), before/after hashes and readback,
  and proof that edits changed bytes. Percent affected = distinct affected bytes
  or blocks divided by an explicitly named partition/data/metadata denominator.
  Report sparse byte changes and whole-block damage as different metrics.
- Original verity parameters/root pins/salts, expected FEC roots (2 here),
  protected data/hash counts, FEC placement and mapping error policy. Do not
  reinterpret two roots as a global two-block or fixed-percent damage budget.
  Interleaving and damage concentration matter; derive targeted patterns from
  the exact kernel/FEC implementation and record that derivation.
- Guest monotonic observation intervals, host monotonic stage times, QEMU virtual
  time if actually measured, host load, cold/warm-cache assumptions and timeouts.
  No conversion of faster host scheduling into physical UART/CPU fidelity.

The [kernel's FEC description](https://docs.kernel.org/admin-guide/device-mapper/verity.html#forward-error-correction)
explains why data/hash/FEC placement and interleaved codeword concentration must
be captured. Recovery claims require observations, not just an intended pattern.

## Injector guards required before implementation

The future injector creates its own overlay with exclusive creation in a new
private run directory; it must not accept an arbitrary writable input image.
Bind a creation token and device/inode/size identity to the file, reject symlinks,
hardlinks/aliases, nonregular files and /dev paths, then validate the entire
backing chain against the expected sealed generation. Refuse reuse, running
guests and shared writable backing nodes. Close injection writers before launch.
Run all qemu tools with explicit formats, private regular-file paths and locks.

Parse and validate the real partition table, reject overflow/out-of-range and
cross-partition writes, and require each requested byte range to be contained
in an allowlisted target extent. Data campaigns cannot damage BOOT, partition
tables, EBRs, trusted root sources or integrity files. Metadata campaigns require
a separately explicit target class and extent list in the disposable overlay;
they never edit the trusted metadata source or derive new acceptance from the
damaged image. Faults in hash/FEC files must use the sealed filesystem's exact
file extents, not random guesses within RECOVERY.

Before injection, read targets and neighboring guards; after injection, read back
exact changes and compare QCOW2 allocations with the declared ranges. Allocation
clusters may contain unchanged neighboring bytes, so compare bytes as well as
allocation maps. Refuse no-op or unexpected changes. After guest shutdown retain
the overlay, raw/verified evidence, timeouts and failures. Never repair or clean
up a failed case as a prerequisite for the next case. Guest runtime LOGS writes
are a separate explicitly allowed range. No physical block-device interface is
part of this design.

## Outcomes are a vector, not a single boot boolean

For every stage/function record PASS, FAIL, NOT_REACHED, NOT_EXERCISED or UNKNOWN
with evidence and time bounds. Aggregate labels may aid navigation but must
retain this vector:

| Axis | Evidence examples |
|---|---|
| Kernel / initramfs / root handoff | Console milestones, mapper creation, verified lower mount |
| systemd / userspace | PID1, two readiness samples, required services and libc calls |
| FSW storage / launch | Verified mount, direct ELF open/exec/loader outcome, RAM vs persistent source |
| Initialization / tasks | Exact ordered names, starts, exits and watchdog messages |
| Housekeeping | Samples with guest timestamps and expected fields |
| Packet generation / routing | Receipt, route, queue and buffer bytes, separately from external TX |
| Filesystem / libraries | Declared read/exec probes with actual EIO/errno and mapper error state |
| Drivers / external fixtures | Bound driver/device availability, actual operations and fixture state |
| Individual FSW functions | Named workload/probe, expected effect, dependencies and observed result |
| Shutdown / evidence | Normal, crashed, timed out, forced kill, or incomplete evidence |

Distinguish clean baseline, observed correction, unrecoverable accessed data,
boot failure, FSW launch failure and degraded function subsets. Uncorrectable but
unaccessed damage needs more than a clean boot: establish unrecoverability using
a separate duplicate-overlay diagnostic read, and demonstrate or explicitly
limit knowledge of the primary workload's accessed set. Probing that damage in
the primary run changes the experiment. A valid sampled verity status does not
certify unread data. Do not scan away this distinction in operational mode.

An intended correctable pattern is only PASS_RECOVERED with correction evidence
and verified output matching the clean source. FEC correction typically does not
heal the backing bytes; inspect raw/verified reads separately. An intended
uncorrectable case can remain UNKNOWN if it was never read or logs are missing.
Booting with a missing subsystem is degraded operation, not boot failure and not
full application success. Existing absent SPI/serial fixtures must be labeled
baseline limitations rather than attributed to corruption.

Start future work with deterministic single-target controls and matched clean
cases, then bounded multi-target/codeword controls after injector review. Large
random sweeps, resealing, new peripherals and hardware operations are outside
Phase10L authorization. Terminate each run with the existing bounded contract;
never lengthen timeouts silently to change a result.

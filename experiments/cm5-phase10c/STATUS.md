# Phase 10C — verified captured V8 userspace reached

**Primary target achieved:** captured physical **6.18.50+rpt-rpi-2712 kernel +
original captured initramfs + original golden partitions/metadata → verified
OS root → systemd PID 1 → active multi-user → verified FSW access**. The final
run powers off normally, and its new LOGS file is independently read back on
the host. The native PCIe stretch target is partial: MDIO and both root ports
work; downstream RP1/link/translation/native MSI do not.

AI-assisted local experiments only, not for upstream contribution. Starting
branch/HEAD remain `cm5-rp1-hardware` /
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. No commit, push, reset, stash, clean,
discard, physical-device operation, EEPROM change, golden overwrite, production
kernel/initramfs patch, root/tree/parity replacement or regeneration occurred.
Previous uncommitted work and evidence remain present.

## Final outcome table

| Objective | Actual outcome | Independent evidence |
| --- | --- | --- |
| Captured 6.18.50 and original initramfs | PASS, original inputs unchanged | input identities and diagnostic_copy=false |
| Native eMMC and all partitions | PASS, ADMA64 in opt-in profile | real driver/card/partition serial output |
| OS and FSW mappings with roots2 | PASS | guest dmsetup tables and two valid statuses |
| Actual verified reads | PASS | diagnostic first-read hashes; final FSW digest equals original p5 block |
| Verified OS filesystem mounted | PASS | kernel UUID plus independent ro,norecovery mapper mount |
| Root switch and systemd PID 1 | PASS | /proc/1/comm and /proc/1/exe from actual OS |
| multi-user.target | PASS | active at guest uptimes 351.71 and 382.73 |
| Verified p5 mounted/read | PASS | actual mapper source, ro,norecovery, V, block digest, directory read |
| Captured FSW executable | UNAVAILABLE | only empty lost+found in captured p5; no regular files |
| Filesystem/library/storage diagnostics | PASS | captured OS Python ELF, libc call, LOGS fsync and readback |
| Peripheral diagnostics | Header UART command/response works; SPI unavailable | second PL011 debug UART; no native RP1 endpoint |
| Normal QEMU shutdown | PASS, exit 0, no timeout | systemctl poweroff and serial Power down |
| Post-exit LOGS persistence | PASS | read-only export/debugfs dump equals 4096-byte test pattern |
| Writes outside LOGS | None observed | all allocated virtual COW extents lie entirely in p6 |
| Native MDIO | PASS within documented subset | timed handshakes, banks/readback, invalid/reset qtests and actual driver |
| Native root ports | Both enumerate [14e4:2712] | real 6.18.50 driver, domains 0001 and 0002 |
| Native RP1/windows/MSI | NOT IMPLEMENTED/NOT VALIDATED | both links down; no endpoint BAR access claimed |
| Preservation | PASS | 19 hardware qtests, 2 generic checks, 24 Phase10A tests, 10 synthetic cases, 5 Phase9 controls |

The final evidence is `artifacts/report-final/result.json`, with a separate
`comparison.json` and per-milestone human summary. This normalized report uses
userspace observations rather than interpreting missing console markers as
failed operations. Earlier raw `run.py` fields named `multi_user` and
`full_scan_complete` are serial-marker-only: their false values do not override
the saved independent userspace evidence. No old result was overwritten.

## What the 900-second stop actually meant

The Phase 10B original log was re-read: its last kernel messages show RECOVERY,
loop0–3 and two verity initializations. It does not reveal the exact process
state at 900 seconds. We cannot retrospectively recover that state.

The bounded faithful-hook diagnostic reproduction now establishes:

1. RECOVERY is read-only with journal replay disabled; its hash/FEC files back
   loop0/1 for FSW and loop2/3 for OS.
2. Both original maps exist, contain `fec_roots 2`, and report `verity V`.
3. First verified 4096-byte reads complete: OS SHA-256
   `6401fa045488cc773681916e0de59b876b49dbe8eaa4db59ed0e78ecdc2bbc15`,
   FSW `3767f788fc318481cc354ee1cf7cd343e4e0610c69f7c29bb58b7e5f024672db`.
4. The unchanged hook reaches its forty-chunk **full 10 GiB verified OS read**.
   Its `dd` is in D state, waiting in `mmc_blk_rw_wait` for PIO or
   `folio_wait_bit_common`/block read for ADMA. Completed-sector counters increase.
   For example the PIO dm-1 counter advances from 34400 sectors at uptime 25.99
   to 117344 at 49.90; this is not guest inactivity or a pure userspace spin.
5. There are no observed FEC correction messages in these clean runs. Valid
   FEC configuration/module availability is not a claim of correction activity.
6. With tested storage fixes the hook progresses through its chunks and the
   unmodified initramfs reaches the verified root mount and systemd.

QMP reports the VM running, but its block byte counters are zero because this
card path does not call block accounting around its synchronous `blk_pread`.
Zero counters are not evidence of zero reads. Guest counters/stacks and bounded
card/batch traces provide the independent observations. Backend batches at
20–22 host seconds, for example, return success for actual 131072-byte reads.
Card consumption and backend lookahead are explicitly different events.

This diagnoses the reproduced virtual stop as very slow forward progress in
the captured verified scan, consistent with the prior 900-second observation.
It does not fabricate an exact old guest stack or attribute the physical
39.36-second interval to FEC. The supplied physical dmesg was rechecked directly:
/init 1.169882, module 1.929681, RECOVERY 1.964308, verity 2.016719, root
41.377123, systemd 41.616488. The unchanged hook's scan is a source-consistent
candidate for that interval; no new physical timing instrumentation occurred.

## Tested fixes, not a timeout-only change

- **SDHCI capability bug:** transfer-mode writes were stripping DMA enable when
  SDMA was absent, even if ADMA2 was advertised and implemented. The gate now
  recognizes SDMA/ADMA1/ADMA2. A new ADMA-only high-address test exposed the bug;
  the actual kernel's first ADMA attempt also timed out before the fix.
- **Opt-in ADMA64:** the existing shared SDHCI DMA engine is enabled through
  `emmc-dma=on`. The default 6.18.62/Phase 9 profile remains PIO. No CQE, HS400,
  tuning or electrical accuracy is advertised.
- **CMD18 transfer overhead:** the card used to return one byte per bus callback
  even for block-sized ADMA reads. It now returns the available requested block
  portion, preserving boundaries and protocol state.
- **Bounded backend batching:** opt-in `x-cmd23-read-batch` performs at most
  128 KiB, limited by explicit CMD23 count and capacity, only for the zero
  boot/RPMB-area eMMC user-area profile. It never survives a command boundary,
  reset or migration load and never falls back to golden host bytes.

The instrumented post-fix scan reached 27/40 chunks by elapsed 158 guest seconds
in one bounded window. That measured progress justified a 420-second budget for
the complete original boot, userspace validation and shutdown. The final run
finished normally in 384.11 host seconds; this is a local result, not a hardware
performance/fidelity claim or a controlled general speedup measurement.

## Actual final transitions and functional evidence

Final original run: `artifacts/c-original-final/`.

| Observation | Guest clock seconds |
| --- | ---: |
| Captured /init | 3.744359 |
| External dm_verity module | 6.492325 |
| RECOVERY mount | 6.628971 |
| Verified OS ext4 UUID mounted on dm-1 | 242.384937 |
| systemd 257.13 PID 1 starts | 246.086784 |
| Verified FSW UUID mounted on dm-0 | 264.129141 |
| Independent multi-user active queries | 351.71, 382.73 |
| Normal Power down | 387.829617 |

Guest and host clocks are not interchangeable. The final original console does
not print all hook progress lines; complete-scan handoff is inferred from the
unchanged hook's gating logic plus the observed verified root/userspace, not
represented as a byte-by-byte trace of all 10 GiB. The diagnostic copies do log
the original progress file and actual read counters.

The debug UART uses stock systemd's command-line debug-shell interface after
root handoff. It does not replace PID 1, verification, root flags or the default
target. The successful run has **diagnostic_copy=false** and the original
initramfs SHA-256 `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`.
Its kernel SHA-256 remains `154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d`.

`userspace.json` independently records both tables/statuses, OS and FSW
`ro,noatime,norecovery` mounts, PID 1 executable, active target, root Python ELF
hash, libc getpid call, verified FSW read/listing and LOGS fsync/readback. The
kernel's root ELF is actually fetched from the verified captured OS; the public
observer script is lab code, not proprietary flight software.

The post-exit LOGS test file SHA-256 is
`5ab775379b00e0ca28b6ee8c0b71b2e54307875de77c156356740d946a181be6`.
All virtual overlay extents are within p6. These are observations for this run,
not a general write-protection or physical power-loss model. Golden and all
physical boot input identities compare unchanged before/after.

## Native PCIe advance and remaining stretch work

Source research used official Raspberry Pi 6.18.50 tag `stable_20260911`, commit
`cff533aec2fa601846766b32ff57204e0a61bed7`, with recorded URLs/SHAs outside the
repo. The exact distro build provenance beyond that tag remains unestablished.
The actual captured executable corroborates the exercised register sequence.

MDIO has timed port0 transactions, 0x1600/0x1100 bank state, reference-clock
register readback, logical PLL/SSC state, busy arbitration, read-only completion,
reset cancellation and observable invalid-operation timeouts. It does not return
immediate success for arbitrary requests or turn PLL programming into link-up.
The new native root-port class uses PCI-core configuration/bridge semantics and
the BCM2712 IDs/capability offsets. Both actual native drivers now get past MDIO
and enumerate `0001:00:00.0` and `0002:00:00.0` as `[14e4:2712]` type-1 root ports.

Both native links remain down because downstream routing, endpoint attachment
and window translation are absent. Native RP1 BAR assignment and MSI are not
claimed. Physical controller addresses/domains/interrupt descriptors are retained,
but apertures remain explicit reduced lab descriptors. INTx is wired; native
interrupt traffic is unvalidated. Existing GPEX, RP1 BAR0/1/2 and MIP/SPI fallback
tests remain. Thus this is a real native driver advance, not full native PCIe.

## Captured FSW investigation

Read-only `qemu-img` export of actual p5 followed by non-writing `debugfs` shows
only inode 11 `/lost+found`, directory mode 040700, itself empty. No regular files
or suitable executable exist in this captured filesystem. The audit records its
partition SHA-256 and expected block hash without copying private file content
into the repo. The verified guest sees the same directory and block digest.
No synthetic FSW, resealing or parity replacement was introduced.

## Preservation, incomplete evidence and next priorities

- 19 focused qtests PASS: RP1 6, cm5io/root/MDIO 4, MIP 3, SDHCI 6.
- Generic platform and PCI SDHCI register checks: 2 PASS.
- Phase 10A: all 24 unit tests and 10 synthetic cases PASS; its source files
  remain unchanged.
- Phase 9 clean, OS0, OS1 and FSW0 PASS; no-FEC EXPECTED_FAILURE. These still use
  the 6.18.62 lab initramfs/profile with targeted verified reads, not the captured
  forty-chunk pre-root scan. Golden unchanged; no baseline evidence overwritten.
- Final build/style: compiled targets PASS; checkpatch --no-signoff has zero
  errors/warnings. No signoff was invented for local AI-generated work.

Retained unsuccessful attempts include early diagnostic shell `/dev/null` and
nodev `/run` instrumentation failures, the initially exposed ADMA gate defect,
and bounded partial-scan timeouts. None is represented as a successful original
boot. `c-original-debug1` reached userspace but was killed at its original bound;
its raw post-kill LOGS export did not yield the new file without journal replay.
No journal replay or physical power-loss claim was made. The final normal-shutdown
run independently passes host persistence. Artifact IDs remain distinct.

Next: implement source-backed native outbound/inbound windows, indexed downstream
config, a connected RP1 endpoint/link state machine and host-specific MIP DMA/MSI
routing with bounds/reset/interrupt tests. Then test the real RP1 MFD/clock/SPI
dependencies. Add broader host-error/cache/migration coverage before making
claims about those cases. A future approved FSW executable/derived fixture is
needed for application execution; this captured p5 cannot supply one. Keep
GPEX/6.18.62 and Phase 10A firmware-proxy fidelity levels separate.

Exact commands and evidence semantics: [README.md](README.md).

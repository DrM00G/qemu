# Phase 10F.1 status — local experiment, 2026-11-14

**Primary gate achieved: the actual captured 6.18.50 kernel and original
initramfs booted from exact bytes selected from active disposable QCOW2 BOOT,
reached verified multi-user userspace, passed strict native 10kHz SPI, and
preserved LOGS through normal shutdown.** This is not physical firmware
equivalence: generated lab DT and explicit headless configuration substitutions
remain. AI-assisted local experiment only; not eligible for QEMU upstream.

## Preservation and scope

Started in `/home/aweso/projects/qemu`, branch `cm5-rp1-hardware`, HEAD
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. Printed full initial Git status,
read applicable AGENTS.md/code-provenance policy and Phase10F/10E handoffs,
inspected actual selector, validator, reader, runner and preserved test evidence.
No reset, clean, stash, commit or push occurred.

A private source-only checkpoint of all existing modified/untracked source
files (77 paths, excluding artifacts and Python caches), initial diff, status
and source hashes was created before significant edits at:
`/home/aweso/cm5-v8-lab/phase10f1/checkpoint-20261114T084835/`.
Earlier sources and artifacts, including failed attempts, remain preserved.
No hardware implementation or hardware qtest source was edited. No SPI-rate
optimization, FEC corruption sweep, physical storage access, host block-device
access, EEPROM operation or original captured input write was performed.

Independent baseline evidence:
`/home/aweso/cm5-v8-lab/phase10f1/accepted-20261114-02/`.
The whole golden hash matched the established value
`e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.
All five physical capture file hashes matched `physical-boot.sha256`, and the
same five files read through QEMU from golden-backed BOOT matched those separate
captures. Overlay sources/README/map were accepted independently before faults;
the selector never creates its acceptance hashes from a faulted overlay.

## Archive and config blockers resolved

The original initramfs validates as two complete newc archives, 1,091 entries,
with an initial uncompressed archive, zero padding, then a complete zstd frame.
No archive paths are extracted onto the host; no bytes are repacked or changed.

| Identity | SHA256 / bytes |
| --- | --- |
| Original stored initramfs | `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`, 23,455,255 |
| zstd frame at offset 5,192,704 | `d3357fee5563919d0feddc909d65bd9483061471972ab2a03a583aafba7e5b8a`, 18,262,551 |
| Decoded zstd contents | `53a9a5df5cadba05da9719869096a93646ce45ab054c1f8ce55c53a74ca85d48`, 57,997,824 |
| Aggregate decoded stream, including padding | `94ce23cb8923f395f65a8a52782d4bc166d4d1570734946079d26118856dae17`, 63,190,528 |

Bounded stable libzstd streaming uses a 64MiB window maximum, 64KiB output
chunks and 128MiB aggregate decoded limit; advertised frame sizes never drive
an allocation. Frame termination/checksums and decoded archive entries,
boundaries, padding and trailers are checked. Unsupported, truncated,
malformed and overexpanded inputs fail closed. Complete frame/archive validity
is not proof of execution; actual execution has independent guest evidence.

The opt-in `cm5-headless-lab` config profile declares the known CM5/official IO
identity. Both `[cm5]` and `[pi5]` match; `[cm4]` does not. Bounded textual
includes, precedence, explicit selectors, supported defaults and final
auto-initramfs state are handled. The original config selects its explicit
kernel/initramfs/cmdline and the known-board default CM5 DTB. Unknown active
directives/values and unsupported conditionals still stop selection.

Every active config operation has a private outcome ledger. Audio, display,
camera, graphics/CMA, USB, framebuffer/overscan and boost operations are
explicit lab substitutions with reduced fidelity, not silently ignored or
claimed faithfully executed. Actual relevant overlay sources and BOOT README
were read and decompiled privately. The overlay map directs BCM2712 KMS to the
pi5 variant; firmware mapping/fixups/parameter application are not implemented.
`nospi10` concerns SoC SPI10, distinct from the deliberately enabled RP1 SPI0
workload. [README.md](README.md) lists all accepted operations and reductions.
[references.json](references.json) pins documentation revision and source hashes.

## Actual captured V8 guest evidence

Clean run: `artifacts/v8-selected-20261114-02/`.
Independent strict hardware report: `artifacts/native-report-20261114-01/`.
Selected-byte/argv/runtime provenance: `artifacts/provenance-20261114-01/provenance.json`.
Private command, exact exports and selection ledger:
`/home/aweso/cm5-v8-lab/phase10c/v8-selected-20261114-02/`.

| Milestone | Fresh outcome |
| --- | --- |
| Same active QCOW2 read for selection and guest | PASS; private logical reads via QEMU, same overlay in actual guest argv |
| Original gzip kernel bytes exported and used | PASS; SHA256 `154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d` |
| Original initramfs bytes exported and used | PASS; exact stored hash above, no diagnostic replacement |
| Actual Linux 6.18.50 starts | PASS; serial identifies `6.18.50+rpt-rpi-2712` |
| Native eMMC | PASS; mmcblk0 and p1/p2/p3/p5/p6/p7 enumerate |
| Original /init executes | PASS; kernel announces /init; original verity setup reaches root handoff |
| Both verity mappings and roots2 | PASS; independent dmsetup status/table observations report V and fec_roots 2 |
| Verified root/FSW mount | PASS; original verified devices mounted read-only, original verification metadata retained |
| systemd PID1 | PASS; executable `/usr/lib/systemd/systemd`, functional original OS Python/libc |
| Independent multi-user active | PASS at guest uptimes 363.35 and 393.64 seconds; over 30 seconds apart |
| Native RP1 | PASS; Gen2 x4, endpoint/chip ID, BAR access, 61 MSI-X vectors, MIP events |
| Strict native SPI at 10kHz | PASS; repeated payloads, IRQs, CS framing and MOSI/MISO hashes; separate strict report all 14 checks pass |
| Normal shutdown | PASS; requested after userspace validation, QEMU exit 0, no timeout |
| LOGS persists after shutdown | PASS; host debugfs extraction matches fsynced guest payload |
| Independently selected-byte/runtime evaluator | PASS, all 16 checks |
| Physical boot-ROM / EEPROM / full firmware equivalence | NOT_IMPLEMENTED, not claimed |

The runner's old `multi_user` field checks only a serial target-message marker
and is false here. Independent `systemctl is-active` observations above are the
authoritative multi-user gate. Likewise its `full_scan_complete` marker is
false: the original archive is unmodified and root handoff is observed, but no
separate stdout full-scan PASS marker was captured. Neither field is relabeled.
Early observations record inactive/time-limited multi-user queries before the
two valid samples; those observations remain intact.

The exported physical DTB hash is
`b297f9516345eb4eb22d22f4c364fcb3705970f28b6d87875583dadf37fbb3ac`.
It is validated/digest-gated/exported, **not executed**. Runtime generated lab DT
is 1,048,576 bytes with hash
`8f9ce2e6c3065b87b0b84e44f3c181192b94a4ee8c01d9352bde3952f13b0e34`.
The observer records model/compatible and DT hash on every sample. Effective
chosen bootargs and `/proc/cmdline` hashes both equal the recorded effective
cmdline hash `3aff4ecd6ca857e716e0e1bf84e094e3c614f146e98eea1945a31d57864b4f85`.
Selected original cmdline hash, whitespace normalization and appended console/
debug arguments are separately recorded. Actual complete argv remains private.

## BOOT faults

Campaign `artifacts/faults-20261114-01/` is gated on the successful clean V8,
clean persistence and native SPI results. Each case creates a fresh private
golden-backed overlay and records mutation, actual runner command and outcome.
Selection, guest launch, kernel entry, root verification and operational
survival are separate fields. **All nine cases PASS.** No physical firmware
failure behavior is inferred.

| Fault | Selection outcome | Guest/root/operational outcome |
| --- | --- | --- |
| Corrupt MBR signature | INVALID_LAYOUT, PARTITION_TABLE | No guest, no kernel entry, root/operation not reached |
| Corrupt p1 geometry | INVALID_LAYOUT, PARTITION_TABLE | No guest, no kernel entry, root/operation not reached |
| Missing selected kernel | SELECTED_FILE_UNAVAILABLE | No guest, no exports, no fallback |
| Invalid selected gzip kernel (CRC mutation) | INVALID_IMAGE, SELECTED_FILES | No guest, no exports, no fallback |
| Missing selected initramfs | SELECTED_FILE_UNAVAILABLE | No guest, no exports, no fallback |
| Malformed selected initramfs | INVALID_IMAGE, SELECTED_FILES | No guest, no exports, no fallback |
| Corrupt selected DTB | INVALID_IMAGE, SELECTED_FILES | No guest, no exports, no fallback |
| Structurally valid changed cmdline | INVALID_IMAGE, LAB_INTEGRITY | Structure passed; separate accepted digest rejected; no guest/exports/fallback |
| Unused issue.txt payload byte | SELECTED | Original kernel/initramfs, both valid maps, verified userspace, strict SPI, normal shutdown and LOGS persistence PASS |

The unused-file mutation is at BOOT byte offset 138,210,304. All selected/config
hashes equal the clean run. It is outside all 674 actual QEMU reader requests,
including 64KiB prefetch (44,171,264 returned bytes). The byte remains corrupted
after normal shutdown, confirmed by a separate sector-aligned QEMU readback.
A one-byte raw offset view was rejected for alignment; the successful bounded
512-byte view and its exact-byte comparison supersede that diagnostic attempt.
The delivered readback helper was also tested against the closed final overlay;
original campaign records are retained unchanged.

The unused-file run independently reports multi-user active at 369.06 and
399.93 seconds and passes the same independent 14-check native report and
16-check selected-byte/runtime evaluator. Evidence:
`artifacts/outside-native-report-20261114-01/`,
`artifacts/outside-provenance-20261114-01/provenance.json`, and
`artifacts/outside-readback-20261114-01.json`.

## Validation and environmental limits

| Fresh check | Outcome |
| --- | --- |
| New config/archive tests, including captured read-only initramfs | 23 PASS |
| Shared Phase10F tests, explicit pipe transport | 20 PASS, including real selected-read EIO and error outside read set |
| Shared Phase10F tests, 64KiB bounded pipe prefetch | 20 PASS |
| Preserved Phase10A / Phase10D / Phase10E host units | 24 / 8 / 3 PASS |
| Preserved Phase10A synthetic matrix | 10 cases PASS at its original evidence level |
| Actual selected synthetic runner and MBR no-launch check | PASS, `artifacts/synthetic-20261114-03/`; synthetic execution is not Linux |
| Unchanged cm5io / RP1 / MIP / SDHCI qtests | Attempted, BLOCKED by sandbox socket bind denial before tests execute |

This sandbox denies Unix socket bind and socket introspection. The first NBD
attempt and initial preserved units failed for that environmental reason.
The first captured launch selected/exported correctly but inherited-socket
control failed before kernel entry. These failures are preserved under
`accepted-20261114-01`, `v8-selected-20261114-01`, and early synthetic/unit logs.
The working path explicitly uses a persistent read-only qemu-io block graph and
FIFO QMP/debug chardevs, with no network/socket listener. Optional 64KiB/2MiB-LRU
prefetch has its actual QEMU read spans in the ledger. There is no automatic
transport fallback or host-asset fallback after a selection error.

The 23 hardware qtests passed in earlier phases, but are not counted as passing
freshly here. Their current abort logs are under
`artifacts/regressions-20261114-01/`. The unchanged hardware baseline is further
exercised by this fresh original-kernel native-RP1/strict-SPI boot. No higher-rate
SPI result or new FEC-corruption result is claimed.

## Remaining work

The supported selection proxy and compatible lab loader are operational for
the captured V8. Physical DT overlays/parameters, real board/attached-device
discovery, prefixes/additional conditional defaults, EEPROM boot-source retries/
fallback/tryboot and firmware authenticity remain separate work. README gives
the concrete sequence for extending these without conflating proxy selection,
guest verification and hardware/firmware equivalence.


## Final source and Git accounting

Final golden and all five captured asset identities exactly match the accepted
before record: `artifacts/final-20261114-01/input-preservation.json`. The 77-path
initial source inventory has no missing files; all hardware, qtest and unrelated
phase source hashes match the private checkpoint. Only eight existing Phase10C/
10F experiment files changed in this session, plus eleven new Phase10F.1 source,
test, reference and documentation files. The earlier substantial dirty tree
remains intact. Final status and preservation inventory are under
`artifacts/final-20261114-01/`; the session-only diff summary is under
`artifacts/source-review-20261114-02/`.

Session changes are bounded initramfs validation, explicit config policy,
private BOOT selection/export provenance, QEMU pipe transport/control options,
original-guest/fault evidence and reproduction tooling. No hardware model or
hardware qtest source changed. Branch/HEAD are unchanged, no changes are staged,
and no commit/push/stash/reset/clean occurred. All launched experiment sessions
finished; selectors reaped their QEMU block readers and both successful Linux
guests powered off normally. No experiment process is intentionally left running.

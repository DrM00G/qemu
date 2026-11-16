# Phase 10A status — 2026-11-13 Hawaii

**Delivery scope: bounded BOOT file reader/validator and provenance harness.**
It is NOT Raspberry Pi firmware. There is no BOOT-to-guest handoff, and no
claim that proxy outcomes predict physical firmware failure behavior. This
uses the bounded-reader alternative explicitly allowed in the request.
AI-assisted local experiment only; not eligible for upstream contribution.

Started and resumed on `cm5-rp1-hardware`, HEAD
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. The six pre-existing untracked
entries were preserved. No existing tracked sources changed, no commit/push,
reset or clean occurred, and no captured input or physical device was modified.

## Delivered

- `preboot.py`: opt-in explicit boot policy; regular-file-only disposable
  full-user-area raw copies outside the checkout; bounded MBR/EBR and FAT16/32
  reads; checksum-validated VFAT names; supported config selection; selected
  file hashes/extents and header checks; explicit failure/unsupported results.
- `controls.py`: unchanged Phase 9 controls with unique output/lab basenames,
  golden and post-exit overlay identities, physical guest corruption sectors,
  original verity/FEC/diagnostic checks, QEMU status and card-read attempts.
- `audit.py`: host kernel/initramfs provenance, generated DTB origin, and exact
  BOOT range coverage/complement from recorded guest card-read attempts.
- `matrix.py`, `test_preboot.py`: persistent synthetic fault matrix and unit
  tests, including missing-private-image skip behavior and copy protection.
- `README.md`: exact reproduction commands, supported subset, classifications,
  read-observation semantics and limitations.

## Boot source audit

The Phase 9 shell wrapper calls `experiments/cm5-phase6/regress.py`. Its
`-kernel` is `/home/aweso/cm5-phase3-kernel/build/arch/arm64/boot/Image`, the
working 6.18.62 laboratory surrogate. The Phase 3 build pins Raspberry Pi
Linux commit `62a56e350fcfd1c5e204c62dac4ea4ee205eb24e`; no rebuild or kernel
substitution was made here. Each guest run's `inputs.json` records the exact
QEMU, Image and rebuilt initramfs SHA-256, and `command.json` records paths.

For V8 the initramfs is rebuilt from
`experiments/cm5-phase5/artifacts/v8-verified/stage`, patched by the existing
native eMMC/MIP and Phase 9 instrumentation, packed by Phase 3's
`prepare-initramfs.py`, and supplied from the private per-run lab `initrd.gz`.
It is not fetched from that run's BOOT filesystem. The diagnostic executable
is injected into this RAM staging path; it reads verified FSW data but is not
an executable fetched from the verified FSW mount.

`hw/arm/cm5io-dev.c` builds the machine tree with `create_device_tree`, returns
it through `cm5_get_dtb`, and invokes `arm_load_kernel`. It rejects `ms->dtb`
and firmware overrides. The ARM loader subsequently adds boot arguments and
initrd/final DT fixups. There is no external DTB input in these Phase 9
commands. Its exact runtime DTB content hash is unknown; a source hash is not
presented as a runtime DTB hash.

There is no firmware FAT/config selector in the original path. BOOT
`config.txt`, its kernel/initramfs/DTB/cmdline selections, EEPROM boot policy,
overlays and start firmware files are bypassed as boot inputs. The native
guest's `/read-range` probe explicitly reads the first 4096 bytes of p1, and
kernel partition probing also accesses storage. This is not firmware loading
BOOT files. `audit.py` derives exact per-case physical guest byte ranges that
were never even attempted through the card backend; successful returned bytes
cannot be inferred solely from the pre-read trace hook.

In the completed clean/OS0/OS1/FSW0 runs, **762368 unique BOOT bytes** had card
read attempts and **536108544 bytes** had none. The no-FEC early rejection
attempted only 16384 BOOT bytes, leaving 536854528 unattempted. Exact half-open
physical byte ranges are in `boot-coverage-20261113b/result.json`. These are
observed attempts from the guest workload, not simulated firmware reads.

The captured fault-free copy is exactly **15,634,268,160 bytes**. Its reader
parses p1 at sector 16384 (1048576 sectors), p2 at 1064960 (20971520), p5 at
22038528 (1048576), p6 at 23089152 (2097152), p7 at 25188352 (5345279).
MBR p3 is the extended container at 22036480 (8497152 sectors); the Linux
1024-byte p3 node is not the size of the extended MBR container.

The actual BOOT is FAT32. A completed private disposable copy and independent
read-only reinspection both reach `CONFIG_SELECTION`, read **9650 bytes** via
the proxy, and return `UNSUPPORTED: config directive unsupported: dtparam`.
Only `config.txt` was read as a file; its SHA-256 and extents are recorded.
Selection is incomplete, selected files are empty, no QEMU is launched, and
OS/FSW verification and diagnostics are `NOT_REACHED`/`NOT_RUN`. The config is
not silently replaced or partially treated as a physical boot result.

## Test matrix and evidence

| Test | Outcome | Evidence level |
| --- | --- | --- |
| Python unit tests | 24 PASS | Executed host tests, synthetic data |
| Synthetic fault-free BOOT | HEADERS_VALIDATED, UNSUPPORTED handoff | Executed bounded proxy |
| Synthetic corrupt MBR | INVALID_LAYOUT | Executed bounded proxy |
| Missing selected kernel / initramfs / DTB | SELECTED_FILE_UNAVAILABLE, all 3 | Executed bounded proxy |
| Corrupt selected kernel / initramfs / DTB headers | INVALID_IMAGE, all 3 | Executed bounded proxy |
| BOOT corruption outside actual proxy reads | No new failure; HEADERS_VALIDATED | Executed bounded proxy |
| Kernel body corruption after header | Header checks do not detect it; UNSUPPORTED handoff | Executed limitation control |
| Injected read error in selected file | READ_ERROR, zero bytes returned for failed read | Executed unit test, proxy-only fault |
| Error outside reads | No automatic failure | Executed unit test |
| FAT32/VFAT and FAT16 fixtures | PASS | Executed unit tests |
| Config overrides, unsupported directives/boot policy | PASS | Executed unit tests |
| Missing private golden | SKIPPED_WITH_REASON | Executed CLI unit test |
| Copy/inject path and unchanged synthetic golden | PASS | Executed unit test |
| Full-size captured copy | UNSUPPORTED config, no guest launched | Executed host proxy on private copy |
| Full-size captured copy, XOR physical sector 0 | INVALID_LAYOUT after 512 returned bytes; golden unchanged | Executed full-size copy/inject/report path |
| QEMU and 4 qtest targets | Built targets verified, no work required on resume | Compiled binaries |
| RP1 / cm5io / MIP / SDHCI qtests | 5 + 2 + 3 + 4 = 14 PASS | Compiled QEMU qtests |
| Phase 9 clean / OS1 / FSW0 | PASS | Real guest controls, direct boot |
| Phase 9 no-FEC | EXPECTED_FAILURE, root refused | Real guest negative control |
| Phase 9 OS0 first attempt | FAIL: console-interleaved digest fails existing parser | Real guest run, failed evaluator preserved |
| Phase 9 OS0 fresh retry | PASS, original evaluator unchanged | Real guest positive control |

The synthetic matrix uses small FAT fixtures, explicitly not captured V8
disks or full-size hardware images. Only the full-size captured-copy path and
Phase 9 controls use the actual user-area size. There are no proxy-driven V8
guest successes. New qtests were not needed: this delivery adds no QEMU
machine/device code, and all fourteen relevant existing qtests completed.

Evidence directories under `artifacts/` (ignored, local only):

- `verification-final-20261113e/unit.log`: 24 passing unit tests; syntax checks
  and a read-only captured-copy reinspection are also recorded here.
- `synthetic-final-20261113e/`: ten-case matrix, per-run JSON and human summaries.
- `golden-preboot-20261113b/`: complete full-size-copy inspection metadata;
  captured raw copy lives in `/home/aweso/cm5-v8-lab/phase10a/`.
- `captured-confirmation-20261113c/`: corrected selection semantics and
  independent golden/overlay identity comparison, both unchanged.
- `captured-mbr-20261113d/`: full-size captured-copy sector-0 corruption result.
- `qtests-20261113b/`: complete fourteen passing qtests from before interruption.
- `controls-20261113b/`: fresh guest control runs and provenance.
- `controls-os0-retry-20261113d/`: one fresh OS0-only retry; original failed
  evaluation is retained in the first batch.
- `boot-coverage-20261113b/`: per-case boot source and read-range audit.

The first sandboxed qtest attempt failed at Unix socket creation; the complete
rerun outside that sandbox passed. Interrupted `controls-20261113a` has no
completed result, and `golden-preboot-20261113a/emmc.raw` is a partial copy;
neither is counted as PASS. All interrupted files are preserved. A partial
captured copy had been created under the checkout before interruption; new
code rejects that destination, and the old ignored artifact was not deleted.

The first OS0 evaluator failure was isolated to `os1_verified_digest`. The
exact expected SHA-512 is present immediately after its marker, but a kernel
FEC message follows `  -` on the same console line. The unchanged
`profile9.marked_digest` requires the digest to end the line and returned
`None`. All other checks passed, including the target FEC correction,
functional tests, collection and normal QEMU exit. The batch's `FAIL` is
preserved rather than relabeled; the retry has a separate result.
The fresh retry passed every unchanged Phase 9 check. Clean, OS1 and FSW0 also
passed; no-FEC returned the expected root refusal. Golden identities were
unchanged in the five-case batch, OS0 retry, captured clean-copy inspection,
and full-size MBR fault run. The initial five-case batch correctly remains
`FAIL` because it includes the parser failure; the separate retry is `PASS`.

## Residual unknowns and next priorities

1. Extend config handling from actual observed directive semantics with tests
   (including includes, overlays and prefixes) before claiming captured-file
   selection. Keep unknown directives fail-closed as `UNSUPPORTED`.
2. Validate full newc/DTB structures and define optional trusted expected-file
   hashes. Header recognition does not detect arbitrary corruption or establish
   signatures, authenticity, secure boot or bootability.
3. Define an explicit machine-compatible handoff. `cm5io-dev` rejects external
   DTBs; using its generated DTB must be labeled as a substitution, never as
   execution of the selected physical BOOT DTB. Do not bypass faulty BOOT assets
   with pristine host files. Keep GPEX and the 6.18.62 kernel fallback.
4. Native Broadcom PCIe, RP1 BAR2, ADMA64/CQE/HS400 and kernel/module parity
   remain separate work. No device model changes or physical fidelity claims
   are made by this host-side harness.
5. FSW executable provenance still needs a diagnostic actually fetched from
   verified FSW, using an explicitly approved derived/resealed fixture if needed.
6. Private physical evidence has all 16 reference SHA-256 entries verified.
   It describes 6.18.50+rpt-rpi-2712/16K, native Broadcom PCIe with generic PCI
   host disabled, and external dm-verity FEC despite base CONFIG_DM_VERITY_FEC
   being unset. Both physical mappings used roots2. The 39.36-second logging
   gap before verified root mount has no established cause; it is not attributed
   to FEC. No host-wall/guest-time equivalence, failure-rate, performance or
   physical fault prediction is claimed.
7. Make the existing guest digest evaluator robust to asynchronous kernel
   console output while keeping marker-scoped expected digest checks. The
   current parser sensitivity remains documented, not hidden by a retry.

The broader historical Phase 9 ten-guest preservation/8 GiB matrix is not
represented as rerun by the five-case controls wrapper. Existing implementation
and artifacts remain intact. Reproduction commands are in [README.md](README.md).

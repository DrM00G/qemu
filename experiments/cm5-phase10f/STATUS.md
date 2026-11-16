> Historical Phase 10F baseline. Phase 10F.1 extends the shared validator,
> adds an explicit captured-config lab profile and pipe transports. See
> [Phase 10F.1](../cm5-phase10f1/STATUS.md) for current outcomes and limitations.

# Phase 10F status — local experiment, 2026-11-14

**Tested subset delivered: active QCOW2 BOOT reads → bounded selection and
validation → private exact-byte exports → actual Phase10C runner launch.**
A synthetic ARM64 program executes and powers off; BOOT faults prevent launch.
**Captured original V8 BOOT-derived Linux boot is BLOCKED**, not claimed achieved.
Its actual config operations and concatenated zstd initramfs are unsupported.
AI-assisted local research only; none of this output is eligible for upstream
contribution under `docs/devel/code-provenance.rst`.

Started on `cm5-rp1-hardware`, HEAD
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. The substantial existing dirty tree
was inspected and preserved. Earlier phase documents and both Phase10E handoffs
were checked against actual source. No QEMU machine/device source was changed.
No commit/push/stash/reset/clean, physical-device access, mount, EEPROM operation,
credential access, remote upload, or golden/original-asset/verity-metadata write
occurred. Original inputs and previous failed/partial artifacts remain intact.

## Honest milestone table

| Milestone | Synthetic subset | Captured original V8 |
| --- | --- | --- |
| Actual active-overlay logical reads | PASS, QEMU read-only NBD | PASS, same disposable golden-backed QCOW2 |
| Injected QCOW2 BOOT mutations observed | PASS, golden unchanged | No captured mutation required/attempted |
| Successful supported selection | PASS, four explicit files plus config/includes | UNSUPPORTED at config.txt line 11, dtparam |
| Semantic checks beyond headers | gzip stream/CRC; complete newc and DTB token structure; pinned hashes | Kernel gzip/header bounds and DTB structure checked in separate audit; initramfs stops at zstd |
| Selected bytes passed to QEMU | PASS, actual Phase10C runner argv and UART execution | NOT_REACHED |
| Selected original initramfs executed | NO, synthetic program does not consume initramfs | NOT_REACHED |
| DT substitution | Explicit generated lab DT; selected DTB hash recorded, selected DTB not executed | Would require the same explicit substitution; no launch |
| Actual BOOT fault prevents guest launch | PASS, corrupt MBR; required-file/config/block-error negatives also tested | Unsupported config prevents guest launch, not a faulted Linux run |
| Verified systemd / both verity maps | NOT_APPLICABLE, tiny non-Linux program | NOT_RUN in Phase10F |
| Independent native RP1 / strict 10 kHz / LOGS persistence | NOT_RUN on synthetic program | NOT_RUN on selected BOOT; earlier accepted baseline preserved |
| EEPROM execution / boot-source fallback / firmware authenticity | NOT_IMPLEMENTED | NOT_IMPLEMENTED |

The smoke program emits `PHASE10F_SELECTED_SYNTHETIC_KERNEL_EXECUTED` through
PL011 then invokes PSCI SYSTEM_OFF. It is deliberately nonproprietary and is not
Linux, Raspberry Pi firmware or a substitute for verified V8 guest evidence.
QEMU receives both selected kernel and selected initramfs paths; actual archive
execution is not inferred from supplying `-initrd`. Every successful synthetic
handoff uses the same exact QCOW2 read by the selector, with a generated lab DT.

## Actual captured BOOT audit

Private evidence:
`/home/aweso/cm5-v8-lab/phase10f/f-captured-audit-20261114-01/`.
`audit.json` inventories file names, clusters, directory entries, exact file
extents/hashes, read attempts/returned bytes and the overlay/backing identities.
`active-config.txt` and full directive contents stay private. No host bytes were
staged into BOOT. This is an audit of named **candidates**, not a claim that the
unsupported config completed firmware selection.

The golden user-area size is 15,634,268,160 bytes. The audit actually reads p1
at guest LBA 16384, length 1048576 sectors, as FAT32. `overlays/` exists (cluster
3) and contains 386 enumerated files, including `dwc2.dtbo`, `nospi10.dtbo` and
`vc4-kms-v3d.dtbo` and its pi4/pi5 variants. Existence does not establish correct
overlay application, firmware selection or hardware compatibility.

| Candidate in the same active overlay | Bytes | Comparison with separate captured host file |
| --- | ---: | --- |
| config.txt | 1410 | Exact SHA256 match |
| kernel_2712.img | 10197590 | Exact SHA256 match |
| initramfs_2712-osverified-v8 | 23455255 | Exact SHA256 match |
| bcm2712-rpi-cm5-cm5io.dtb | 79751 | Exact SHA256 match |
| cmdline_2712-osverified-v8.txt | 279 | Exact SHA256 match |

No golden-versus-host mismatch was found for these five files. Hashes and
identities are in private audit/summary/input records. Kernel SHA256 is
`154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d`;
initramfs SHA256 is
`fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`.
No repacking or kernel substitution occurred. The audit compared golden and
all five host identities before/after: unchanged, including golden SHA256
`e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.

The initial audit caught a validator error: it treated ARM64 `image_size` as
stored file length. That old failed audit field is preserved. The corrected
source-grounded check and separate `kernel-validation-corrected.json` /
`kernel-validation-final.json` supersede that field. Full gzip decode/CRC yields
25,872,896 bytes, memory footprint 26,607,616 bytes, decoded SHA256
`7b2ce1544ed18d495c8ad2fb6945d2eb7517df80a2b8af4a62e0884d76d88c78`.
This passes header/memory bounds; it is not instruction validation. The original
DTB passes complete block/token structural validation. The initramfs parser
walks its initial newc archive and explicitly rejects the following zstd segment;
no complete original initramfs validation is claimed.

Exact remaining blockers, without altering captured config or disk:

1. Active `dtparam` and `dtoverlay` semantics and compatible DT transformations.
   The first stop is line 11 (`dtparam`). Relevant selected overlays exist, but
   neither their operations nor parameters are implemented by this proxy.
2. Camera/display auto-detection, automatic initramfs policy, model filters
   `[cm4]`/`[cm5]`/`[pi5]`, graphics/framebuffer/firmware-KMS controls, 64-bit/boost/
   overscan/OTG settings are outside the implemented selector. Known unsupported
   operations are not silently discarded. Several later overrides do not make
   earlier active firmware operations safe to ignore.
3. The subset requires explicit `device_tree=`; captured config relies on a
   model-dependent default instead. Candidate DTB identity is audited, not
   invented as a completed selector result.
4. Bounded zstd frame decoding and complete decoded/concatenated archive
   validation remain absent. A recognized zstd signature returns UNSUPPORTED.
5. A separately accepted lab digest manifest is required before launch even
   after supported parsing. It does not implement firmware cryptographic trust.

`f-captured-runner-stop-20261114-01` and the later
`f-captured-stop-final-20261114-01` actually invoke the opted-in runner. Both stop
at unsupported `dtparam`, with `process.launched=false`, no guest process record,
no exports and no host-kernel fallback. The first used a newly created runner
overlay; the latter uses the exact privately audited QCOW2. A read-only QEMU NBD
server is not counted as a QEMU guest launch. The latter records final source
identities at its own run time, not a retroactive claim about subsequent edits.

## Tests and evidence levels

| Executed check | Outcome |
| --- | --- |
| Phase10F host units, final | 20 PASS |
| Real Phase10C selected synthetic runner, clean | Marker observed; QEMU exit 0, no timeout |
| Real Phase10C selected synthetic runner, corrupt MBR | Exit 1; INVALID_LAYOUT; no guest process |
| Missing selected kernel/initramfs/DTB | SELECTED_FILE_UNAVAILABLE, empty returned selection buffers |
| Corrupt selected headers and compressed payloads | INVALID_IMAGE, no exports/launch |
| Structurally valid selected payload change | Pinned lab digest rejects it |
| Bad FAT geometry, cycles/final-link errors, truncated/oversize files | Rejected |
| Actual QEMU block EIO in selected kernel | READ_ERROR, failed logical request returns zero bytes |
| QEMU EIO outside logical read set | Clean selection remains SELECTED |
| QCOW2 byte mutation outside read set | Clean selection remains SELECTED, file hashes unchanged |
| Unsupported directives/model filters/boot policy | UNSUPPORTED; no guest launch |
| Includes/filters/include cycles and missing lab baseline | Supported cases pass; unsupported/invalid cases stop |
| Export and post-selection disk tamper | Launch gate rejects |
| gzip CRC/expansion, cpio malformed structures, zstd boundary | Tested rejection; zstd stays unsupported |
| Phase10A preserved unit tests | 24 PASS |
| Phase10A unchanged synthetic matrix | 10 cases PASS at its original header-only evidence level |
| Phase10D preserved units | 8 PASS |
| Strict Phase10E SPI trace-validator units | 3 PASS |
| Existing hardware qtests | RP1 7 + cm5io 7 + MIP 3 + SDHCI 6 = 23 PASS |

Final synthetic runner evidence:
`artifacts/f-runner-final-20261114-02/result.json` (PASS), plus its separate clean
and MBR subruns. Exact commands, public harness snapshots, exports and manifest
are under `/home/aweso/cm5-v8-lab/phase10f/f-runner-final-20261114-02/` and its
runner-private `/home/aweso/cm5-v8-lab/phase10c/` subruns. The clean raw runner
correctly reports `OBSERVED_RUN`, no Linux 6.18.50 entry and no validated userspace.
The dedicated smoke evaluator checks synthetic execution rather than relabeling
that as a verified Linux PASS.

Final units: `artifacts/unit-final-20261114-05.log`; preserved earlier unit
attempts retain both failures and smaller test counts. Synthetic fixtures and
per-selection JSON live under unique private `phase10f-tests-*` directories.
Regression logs are `phase10a-unit-20261114-01.log`,
`phase10a-synthetic-20261114-01/`, `phase10d-unit-20261114-01.log`,
`phase10e-unit-20261114-01.log` and `qtests-20261114-01/`.

No new whole FEC sweep or higher-rate SPI experiment ran. The existing original
6.18.50/native-RP1/strict-10kHz V8 baseline and 6.18.62/GPEX/Phase9 baseline were
preserved, not described as freshly booted in Phase10F. The model/test sources
are byte-identical to their start-of-session tracked hashes. Earlier Phase9,
10C/D/E accepted original-kernel/systemd/verity/LOGS results remain their own
historical guest evidence; qtests and these synthetic runs do not replace them.

## Preserved failures and implementation limits

- First NBD tests exposed an overlong Unix socket pathname. New sockets use
  short, unique private directories; the failed logs/fixtures remain.
- Next tests exposed incorrect JSON image-option invocation. A subsequent
  incorrectly placed blkdebug node did not actually arm a read event, so its
  expected-EIO test failed. Final tests place raw over blkdebug over the exact
  QCOW2; they receive actual QEMU EIO. No Python exception is passed off as
  backend error evidence.
- First actual synthetic loader attempt was rejected by eMMC's power-of-two
  capacity rule. The next fresh **synthetic** fixture uses 4 MiB. No captured
  disk size or golden file changed.
- First Phase10C synthetic run exited during QMP negotiation, exposing an
  existing initialization race. The runner now records that QMP error and
  continues draining serial/collecting process exit. Fresh smoke reruns pass.
- Initial captured ARM64 memory-size classification was wrong; it is preserved
  and superseded by the corrected validation above and a dedicated unit test.

Still absent: EEPROM instruction execution, real boot-source fallback,
firmware signatures/authenticity, real DT overlays/parameters, zstd initramfs
validation, model-dependent defaults, final runtime DT hashing, hostile-host
TOCTOU protection, and proof that arbitrary kernel instructions or initramfs
programs will boot. Supported syntactic validation plus pinned lab digests is
an explicit experimental acceptance contract, not firmware or secure boot.

## Final change and worktree accounting

New Phase10F sources: `block_reader.py`, `validate.py`, `handoff.py`,
`captured_audit.py`, `test_handoff.py`, `synthetic-kernel.S`, `synthetic_launch.py`,
`runner_smoke.py`, `.gitignore`, README and STATUS. All data outputs are ignored;
private media/export/config/manifest data stays outside the repository.

The only earlier experiment source edited is Phase10C `run.py`: opt-in policy,
lab baseline and exact-overlay arguments; fail-closed selector/export/prelaunch
checks; private selected command recording; selected provenance; and the tested
QMP negotiation-race fix. Existing direct-host/recovery/native-SPI profiles remain
available. Phase10A reader/tests and all hardware implementation files remain
unchanged by this session. `qemu-nbd` was built in the existing configured tree.

Initial Git status/diff and tracked-file hashes are in
`artifacts/initial-20261114-01/`. Final status, source inventory, preservation
check, index identity and process audit are in `artifacts/final-20261114-02/`.
No pending experiment/QEMU/test/build process is intentionally left running.

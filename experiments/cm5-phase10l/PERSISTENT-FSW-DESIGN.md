# Future sealed persistent-FSW lab image — design only

No image reseal, repartitioning or new FSW installation is performed in Phase10L.
The current protected FSW filesystem contains only lost+found. Uploading an ELF
to executable tmpfs proves that the captured OS can load and run that ELF. It
does not prove that a damaged protected FSW partition can supply the executable.
Future tests must execute an intentionally installed ELF directly from the
read-only verified FSW mount, without a separate RAM copy rescuing it.

The design preserves dm-verity's per-access checks and FEC; unrecoverable accessed
data must still fail. This follows the [kernel dm-verity documentation](https://docs.kernel.org/admin-guide/device-mapper/verity.html).
No physical timing or secure-firmware authenticity claim follows from this lab
chain of trusted hashes and explicit derived artifacts.

## Exact prerequisite inventory

Record and lock before a separate sealing authorization:

- Original complete regular-file eMMC capture, byte length, full SHA256,
  partition table/EBRs, partition offsets and lengths in 512-byte sectors.
- Accepted original filename-to-SHA256 BOOT manifest and its own SHA256;
  selected config/includes, kernel, DT/overlays, cmdline and initramfs identities.
- Approved AArch64 ELF SHA256, size, ELF headers, interpreter, DT_NEEDED,
  RPATH/RUNPATH and expected launch path/user/working directory. Never use ldd
  to execute an untrusted cross-architecture input. Audit with readelf instead.
- Existing FSW ext4 UUID, geometry, free space, features, journal/clean status,
  mount policy, executable permissions and dependencies. Inspect OS loader and
  library availability without editing OS. No writable raw guest fallback.
- Exact verity tables for OS and FSW: version 1, SHA256, 4096-byte data and hash
  blocks; OS 2621440 data blocks, FSW 131072 data blocks; hash start block 1;
  FEC roots 2, FEC start 0; current protected counts OS 2642083, FSW 132105.
  Preserve the actual root hashes, salts and all parameters in private inventory.
  Current values come from baseline runtime, not tool defaults or a new guess.
- RECOVERY filesystem geometry/free space and actual extents/lengths for
  `/cm5-verity-v2/os/{os.hash,os.fec}` and
  `/cm5-verity-v2/fsw/{fsw.hash,fsw.fec}`; verity superblock dumps and file hashes.
- Initramfs `/etc/cm5-verity/{os.roothash,fsw.roothash}`, all verity hooks and
  original late-hook mount assertions. Preserve OS metadata bytes and root pin.
- Tool binaries/versions/options: qemu-img/io, debugfs, e2fsck, veritysetup with
  FEC support, readelf, initramfs/newc tooling and any filesystem editor. Host
  veritysetup --help and its installed man page define the actual local options.
- Space for a distinct 15634268160-byte logical lab image, extracted regular-file
  partitions and immutable metadata generations. Record host free space first.
- New explicit sealed-image policy binding every changed artifact to the
  intentionally requested ELF version. Do not weaken Phase10L's fixed original
  initramfs construction gate to admit this different future generation.

Phase10L private prerequisite-inventory.json records available table, partition,
export and tool observations. Exact metadata-file dumps/extents, free-space/FS
cleanliness inspection and a sealed-image policy are still prerequisites, not
completed validations. Full private hashes/UUIDs stay outside the checkout.

## Proposed sealing sequence

1. Refuse block devices, symlinks, hardlink aliases and paths inside the checkout.
   Make a new exclusively created regular-file lab image from the verified golden;
   never open the golden for write. Inventory original and output identities.
   Extract FSW and RECOVERY partitions into separate regular files using validated
   byte ranges; no /dev/loop, physical eMMC or host mounts are required.
2. Check the derived FSW filesystem offline. Install only the approved ELF and
   deliberately specified configuration into that private filesystem using a
   reviewed regular-file editor. Keep existing UUID/geometry when possible.
   Verify contents, mode, path and dependencies. Any filesystem repair must occur
   before sealing, be recorded, and never operate on the original capture.
3. Freeze FSW bytes. Use veritysetup format on that regular-file FSW data with new
   regular hash/FEC outputs, format 1, SHA256, 4096-byte blocks, 131072 data blocks
   and two FEC roots. Explicitly record salt, UUID, offsets, generated root and
   command/tool identity; do not rely on random unrecorded defaults. Account for
   the verity superblock versus runtime hash-start convention. Inspect the output
   with dump and verify against the generated trusted root before assembly.
4. Put only the new FSW hash/FEC generation into the derived RECOVERY filesystem.
   Preserve OS hash/FEC files byte-for-byte. The containing RECOVERY filesystem
   may change allocation metadata; its identity is therefore new. Recheck capacity,
   clean state, exact metadata file contents and absence of unwanted changes.
5. Construct a separately named sealed-generation lab initramfs replacing ONLY
   the FSW root pin with the new trusted root (and retaining explicit strict vs
   operational scan policy). OS root pin and all OS verification remain original.
   This is a different derivative from Phase10L's exact operational artifact.
   Record all effective entries and reject undeclared duplicates/overrides.
6. Assemble only the derived FSW/RECOVERY ranges into the new regular-file image.
   If firmware-selected BOOT contents are updated to reference the sealed
   initramfs, update only that derived BOOT and generate a new lab acceptance
   manifest/provenance. If a lab direct-initramfs substitution is used, label it
   explicitly; do not call it firmware-selected original BOOT. Preserve the
   original kernel/config identities unless an independently justified dependency
   actually changes. No partition resizing is planned.
7. Verify the complete image, unchanged OS partition and metadata, new FSW pin,
   boot dependencies and read-only mount behavior. Seal read-only with an
   immutable inventory generation. Run a fresh clean QCOW2 child through strict
   assurance once and a short direct-from-/opt/fsw launch. Strict scans OS only;
   separately verify all FSW data during sealing. Do not reseal after injection.
8. Corruption experiments use fresh children of that sealed generation. Updating
   FSW requires a new intentional stage-and-seal request and new generation;
   a normal experiment must never auto-install an ELF or regenerate trusted hashes.

No executable format/reseal commands are supplied as an automatically runnable
pipeline here: missing geometry/extents/policy inputs must be resolved first.
Format/verify action syntax and FEC options were checked against the installed
veritysetup tool; final commands must bind all paths to owned regular files.

## Measurement consequences

Pre-reading/hashing the entire ELF in a damaged guest forces extra accesses and
can turn latent damage into launch failure. The sealed generation's pre-injection
hash establishes the approved file identity; future direct-launch tests should
declare whether they pre-read the ELF or allow normal demand paging. Likewise
library inventory, filesystem traversal and diagnostic probes alter the accessed
set. Define a primary workload and separate optional probes. Cached code/data can
continue while a later fault terminates the process; record both task-level
outcomes and process lifetime, without inventing independent task survival after
an unhandled process-wide fault. RAM-staged and protected-FSW results stay separate.

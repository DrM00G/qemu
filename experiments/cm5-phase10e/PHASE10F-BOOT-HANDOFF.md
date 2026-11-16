# Phase 10F BOOT-to-runner boundary (source inspection only)

Phase 10E still boots captured host `kernel_2712.img` and the original host
initramfs directly, with the machine-generated DT. Native PCIe success does not
execute EEPROM firmware or make BOOT bytes affect this launch path.

Current Phase 10A `preboot.py` is a bounded regular-file MBR/FAT reader. Its
`Reader.read()` ledger records returned bytes, and `FAT.file()` returns file
contents and records hashes/extents. `probe()` currently discards those buffers
after header checks and ends UNSUPPORTED, without a guest handoff. The captured
config stops earlier at unsupported `dtparam`. It also rejects compressed/ELF
kernels; the actual captured `kernel_2712.img` is gzip. The initramfs is concatenated
newc + zstd/newc, and the existing header-only recognizer is not a complete
archive validator. No phase here changes those classifications.

Actionable next slice, retaining a separately named firmware-BEHAVIOR proxy:

1. Refactor `Reader` behind bounded pread and size interfaces. Supply a read-only
   logical view of the exact per-run QCOW2 overlay, including fault allocations,
   via a QEMU block reader or bounded `qemu-img` raw-offset views. Do not give FAT
   the golden backing path, mount a filesystem, or copy and inspect a different
   image state. Record overlay chain/identity and freeze writes during selection.
2. Add explicit captured-config semantics and tests. Unknown `dtparam`,
   `dtoverlay`, includes, conditions or boot-order actions must still stop as
   UNSUPPORTED. Header recognition cannot turn unsupported selection into boot.
   Keep the explicit emmc-only lab policy distinct from captured EEPROM0xf14.
3. Return selected kernel/initramfs/cmdline/DTB byte buffers from the *completed*
   selection, with per-file provenance, returned-byte ledger and hashes. Add
   bounded gzip ARM64 Image handling and full concatenated initramfs validation.
   Malformed/missing/read-fault cases have no pristine-host-file fallback.
4. Materialize only successfully selected bytes as exclusive private per-run
   files outside the checkout; record that these are BOOT-reader exports, not
   pristine original paths. Feed those kernel/initramfs paths and selected
   command line into a refactored Phase 10C runner. Check export hashes again
   before launch, keep the same disk overlay, and never silently reopen the
   original captured boot files after a selection fault.
5. Resolve DT compatibility explicitly: cm5io-dev rejects external DTBs and the
   physical tree advertises hardware not implemented here. A generated lab DT
   remains a declared fidelity substitution, not execution of the selected DTB.
   A future supported transformation must validate/apply each selected operation,
   record input/output hashes and reject unsupported nodes/overlays. Do not
   blindly accept the live captured tree or silently ignore its directives.
6. Gate this integration with fault-free synthetic handoff, selected-file header
   and payload failures, unavailable files, real reader errors, no-fallback
   checks and a BOOT fault outside the actual read set. Only then attempt a
   captured BOOT-selected guest, with its own fidelity label and boot milestones.

The current source dependency is `Phase10C run.py -> host assets`. The proposed
new dependency is `active overlay -> bounded selector -> validated byte exports
-> compatible lab loader -> same overlay`. EEPROM instruction execution,
cryptographic firmware authenticity and real hardware boot-policy equivalence
remain outside this bounded proxy's claim.

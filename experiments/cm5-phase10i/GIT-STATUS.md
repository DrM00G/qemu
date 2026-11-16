# Final Git state

Local AI-assisted experimental work only; not for upstream contribution. Branch
cm5-rp1-hardware, unchanged HEAD
872181e1de29acb4c13ffdd8937ee6c9fa7d11bd. No staged changes, commit, push,
reset, clean, stash, destructive checkout or pull. All earlier untracked paths
remain present. The initial dirty-source checkpoint is private source/ and
source-hashes.json.66/72 source hashes are identical; six files intentionally
extended for I; none missing. All H files and SPI core/header/traces unchanged.

Complete per-file staged/unstaged/untracked status (including older artifact
files) is [git-status-final.txt](/home/aweso/cm5-v8-lab/phase10i/i-20261116T190606Z/git-status-final.txt). Full
unstaged source diff is [git-diff-final.patch](/home/aweso/cm5-v8-lab/phase10i/i-20261116T190606Z/git-diff-final.patch).
The final summary counts 23 tracked modifications and
25281 untracked files; most untracked files predate I.
The directory-collapsed view below is for review, not the complete inventory.

```text
 M experiments/cm5-phase10c/run.py
 M experiments/cm5-phase10e/native_profile.py
 M experiments/cm5-phase10f1/runtime_observe.py
 M experiments/cm5-phase10f2/boot_policy.py
 M experiments/cm5-phase10f2/build-dt-tools.sh
 M experiments/cm5-phase10f2/dt_pipeline.py
 M experiments/cm5-phase10f2/test_dt.py
 M experiments/cm5-phase10f2/test_policy.py
 M hw/arm/bcm2712-pcie.c
 M hw/arm/cm5io-dev.c
 M hw/arm/trace-events
 M hw/gpio/meson.build
 M hw/gpio/trace-events
 M hw/intc/bcm2712-mip.c
 M hw/intc/trace-events
 M hw/misc/rp1-pci.c
 M hw/misc/trace-events
 M hw/ssi/dw-apb-ssi.c
 M hw/ssi/trace-events
 M include/hw/arm/bcm2712-pcie.h
 M include/hw/ssi/dw-apb-ssi.h
 M tests/qtest/cm5io-test.c
 M tests/qtest/rp1-test.c
?? experiments/cm5-phase10f2/NEXT-SESSION.md
?? experiments/cm5-phase10f2/README.md
?? experiments/cm5-phase10f2/STATUS.md
?? experiments/cm5-phase10f2/runtime_compat.py
?? experiments/cm5-phase10f2/test_runtime.py
?? experiments/cm5-phase10f2/toolchain.json
?? experiments/cm5-phase10g/
?? experiments/cm5-phase10h/
?? experiments/cm5-phase10i/
?? experiments/cm5-phase8/artifacts/
?? experiments/cm5-phase9/artifacts/
?? hw/gpio/rp1-gpio.c
?? include/hw/gpio/rp1-gpio.h
```

Complete tracked diff from HEAD, including inherited F.2/G/H work:

```text
 experiments/cm5-phase10c/run.py              |  69 +++-
 experiments/cm5-phase10e/native_profile.py   |   7 +-
 experiments/cm5-phase10f1/runtime_observe.py |  13 +
 experiments/cm5-phase10f2/boot_policy.py     |  18 +-
 experiments/cm5-phase10f2/build-dt-tools.sh  |   8 +
 experiments/cm5-phase10f2/dt_pipeline.py     |  82 ++++-
 experiments/cm5-phase10f2/test_dt.py         |  58 ++++
 experiments/cm5-phase10f2/test_policy.py     |  66 ++++
 hw/arm/bcm2712-pcie.c                        |  10 +-
 hw/arm/cm5io-dev.c                           |  47 +++
 hw/arm/trace-events                          |   1 +
 hw/gpio/meson.build                          |   1 +
 hw/gpio/trace-events                         |   4 +
 hw/intc/bcm2712-mip.c                        |   3 +
 hw/intc/trace-events                         |   2 +
 hw/misc/rp1-pci.c                            |  88 ++++-
 hw/misc/trace-events                         |   4 +
 hw/ssi/dw-apb-ssi.c                          | 100 +++++-
 hw/ssi/trace-events                          |   3 +
 include/hw/arm/bcm2712-pcie.h                |   2 +-
 include/hw/ssi/dw-apb-ssi.h                  |   6 +
 tests/qtest/cm5io-test.c                     | 126 ++++++-
 tests/qtest/rp1-test.c                       | 480 +++++++++++++++++++++++++++
 23 files changed, 1171 insertions(+), 27 deletions(-)
```

I-only hardware delta relative to the initial working tree:10 files,+649/-8
lines, including the new GPIO source/header and five qtests. The C/G guest
runners also gain an opt-in flag/observer/source capture; I documentation,
comparison tooling and normalized evidence are new. Default SPI/timing/eMMC and
H evidence were preserved. The source-only pre-edit checkpoint and each guest's
private execution-source snapshot permit independent comparison.

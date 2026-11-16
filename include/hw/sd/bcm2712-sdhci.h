/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local experiment; not for upstream submission. */
#ifndef HW_SD_BCM2712_SDHCI_H
#define HW_SD_BCM2712_SDHCI_H

#include "hw/sd/sdhci.h"

#define TYPE_BCM2712_SDHCI "bcm2712-sdhci"
OBJECT_DECLARE_SIMPLE_TYPE(BCM2712SDHCIState, BCM2712_SDHCI)

struct BCM2712SDHCIState {
    SysBusDevice parent_obj;
    SDHCIState core;
    MemoryRegion host, cfg;
    uint32_t ctrl, pin_sel, cq_cap, max50;
    bool dma;
};
#endif

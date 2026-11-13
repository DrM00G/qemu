/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local research, not intended for upstream submission. */
#ifndef HW_INTC_BCM2712_MIP_H
#define HW_INTC_BCM2712_MIP_H

#include "hw/core/sysbus.h"

#define TYPE_BCM2712_MIP "bcm2712-mip"
OBJECT_DECLARE_SIMPLE_TYPE(BCM2712MIPState, BCM2712_MIP)

struct BCM2712MIPState {
    SysBusDevice parent_obj;
    MemoryRegion regs, doorbell;
    qemu_irq irq[64];
    uint64_t edge, mask_host, mask_vpu;
    uint32_t first_vector, num_vectors;
};
#endif

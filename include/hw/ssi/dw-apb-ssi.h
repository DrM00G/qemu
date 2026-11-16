/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Local research model; AI-assisted, not intended for upstream submission. */
#ifndef HW_SSI_DW_APB_SSI_H
#define HW_SSI_DW_APB_SSI_H

#include "hw/core/qdev.h"
#include "system/memory.h"
#include "hw/ssi/ssi.h"
#include "qemu/timer.h"

#define TYPE_DW_APB_SSI "dw-apb-ssi"
OBJECT_DECLARE_SIMPLE_TYPE(DWAPBSSIState, DW_APB_SSI)

/* Experimental synthesis choice, not a measured RP1 FIFO depth. */
#define DW_SSI_FIFO_DEPTH 64

struct DWAPBSSIState {
    DeviceState parent_obj;
    MemoryRegion mmio;
    SSIBus *bus;
    qemu_irq irq;
    QEMUTimer *timer;
    uint32_t regs[0x100 / 4];
    uint32_t tx[DW_SSI_FIFO_DEPTH];
    uint32_t rx[DW_SSI_FIFO_DEPTH];
    unsigned tx_head, tx_count, rx_head, rx_count;
    uint32_t errors;
    uint32_t shift_tx;
    unsigned shift_bits;
    bool shift_busy, irq_level;
    unsigned diagnostic_left;
    uint64_t input_hz;
    uint32_t active_cs;
};
void dw_apb_ssi_set_frequency(DWAPBSSIState *s, uint64_t hz);
#endif

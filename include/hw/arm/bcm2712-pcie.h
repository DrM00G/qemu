/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local research, not for upstream submission. */
#ifndef HW_BCM2712_PCIE_H
#define HW_BCM2712_PCIE_H

#include "hw/core/sysbus.h"
#include "hw/pci/pci_host.h"
#include "qemu/timer.h"
#define TYPE_BCM2712_PCIE "bcm2712-pcie-probe"
OBJECT_DECLARE_SIMPLE_TYPE(BCM2712PCIeState, BCM2712_PCIE)

typedef struct BCM2712PCIeWindow {
    MemoryRegion mr;
    BCM2712PCIeState *host;
    hwaddr base, size;
} BCM2712PCIeWindow;

struct BCM2712PCIeState {
    PCIHostState parent_obj;
    MemoryRegion mmio;
    MemoryRegion pci_mem, pci_io;
    MemoryRegion dma_root;
    MemoryRegion *msi_target;
    AddressSpace pci_as, dma_as, msi_as;
    BCM2712PCIeWindow outbound[2];
    PCIDevice *root_port, *endpoint;
    bool connect_rp1, link_up;
    QEMUTimer *link_timer;
    qemu_irq intx[4];
    uint32_t controller;
    uint64_t ram_size;
    uint32_t regs[0x9310 / 4];
    QEMUTimer *mdio_timer;
    uint16_t mdio_page;
    uint16_t phy_xosc[32], phy_ssc[32];
    uint8_t mdio_reg;
    bool mdio_busy, mdio_armed, mdio_read;
};
#endif

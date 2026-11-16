/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * AI-assisted local BCM2712 PCIe probe groundwork, not for upstream.
 * Contract: raspberrypi/linux pcie-brcmstb.c bcm2712/7712 register layout.
 * Logical endpoint/link, indexed configuration and programmed address windows.
 * MDIO has banked state. No electrical PHY, autonomous training, peer DMA,
 * ATS/IOMMU isolation or migration fidelity is claimed.
 */
#include "qemu/osdep.h"
#include "hw/arm/bcm2712-pcie.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/irq.h"
#include "hw/pci/pci.h"
#include "hw/pci/pcie_port.h"
#include "hw/pci/pci_bridge.h"
#include "system/address-spaces.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "trace.h"

static bool bcm2712_phy_xosc_reg(unsigned reg)
{
    return reg == 0x16 || reg == 0x17 || reg == 0x18 || reg == 0x19 ||
           reg == 0x1b || reg == 0x1c || reg == 0x1e;
}

static bool bcm2712_refclk54(BCM2712PCIeState *s)
{
    return s->phy_xosc[0x16] == 0x50b9 && s->phy_xosc[0x17] == 0xbda1 &&
           s->phy_xosc[0x18] == 0x0094 && s->phy_xosc[0x19] == 0x97b4 &&
           s->phy_xosc[0x1b] == 0x5030 && s->phy_xosc[0x1c] == 0x5030 &&
           s->phy_xosc[0x1e] == 7;
}

/* Logical connectivity, not an electrical PHY simulation. */
static bool bcm2712_link_ready(BCM2712PCIeState *s)
{
    PCIDevice *rp = s->root_port;

    return s->endpoint && qdev_is_realized(DEVICE(s->endpoint)) &&
           bcm2712_refclk54(s) && !(s->regs[0x9210 / 4] & 2) &&
           (s->regs[0x4064 / 4] & 4) && !(s->regs[0x4304 / 4] & 8) &&
           !(pci_get_word(rp->config + PCI_BRIDGE_CONTROL) &
             PCI_BRIDGE_CTL_BUS_RESET) &&
           !(pci_get_word(rp->config + rp->exp.exp_cap + PCI_EXP_LNKCTL) &
             PCI_EXP_LNKCTL_LD);
}

static void bcm2712_link_complete(void *opaque)
{
    BCM2712PCIeState *s = opaque;

    s->link_up = bcm2712_link_ready(s);
    pci_set_word(s->root_port->config + s->root_port->exp.exp_cap +
                 PCI_EXP_LNKSTA, s->link_up ?
                 (PCI_EXP_LNKSTA_DLLLA | (4 << 4) | 2) : 0);
}

static void bcm2712_link_update(BCM2712PCIeState *s)
{
    if (!bcm2712_link_ready(s)) {
        timer_del(s->link_timer);
        s->link_up = false;
        pci_set_word(s->root_port->config + s->root_port->exp.exp_cap +
                     PCI_EXP_LNKSTA, 0);
    } else if (!s->link_up && !timer_pending(s->link_timer)) {
        /* Bounded virtual scheduling convention, not measured link latency. */
        timer_mod(s->link_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 1000000);
    }
}

static PCIDevice *bcm2712_config_device(BCM2712PCIeState *s)
{
    uint32_t index = s->regs[0x9000 / 4];
    unsigned bus = index >> 20;
    unsigned devfn = (index >> 12) & 0xff;

    bcm2712_link_update(s);
    if (!s->link_up || !bus || (index & 0xfff)) {
        return NULL;
    }
    return pci_find_device(PCI_HOST_BRIDGE(s)->bus, bus, devfn);
}

static uint64_t bcm2712_ibar_size(unsigned code)
{
    if (code >= 0x1c) {
        return UINT64_C(1) << (12 + code - 0x1c);
    }
    if (code >= 1 && code <= 21) {
        return UINT64_C(1) << (15 + code);
    }
    return 0;
}

static unsigned bcm2712_bar_offset(unsigned bar)
{
    return bar <= 3 ? 0x402c + (bar - 1) * 8 : 0x40d4 + (bar - 4) * 8;
}

static unsigned bcm2712_remap_offset(unsigned bar)
{
    return bar <= 3 ? 0x40ac + (bar - 1) * 8 : 0x410c + (bar - 4) * 8;
}

static MemTxResult bcm2712_pci_access(AddressSpace *as, hwaddr addr,
                                     uint64_t *value, unsigned size,
                                     MemTxAttrs attrs, bool write)
{
    uint8_t bytes[8];
    MemTxResult result;
    unsigned i;

    if (write) {
        for (i = 0; i < size; i++) {
            bytes[i] = *value >> (i * 8);
        }
        return address_space_write(as, addr, attrs, bytes, size);
    }
    memset(bytes, 0xff, sizeof(bytes));
    result = address_space_read(as, addr, attrs, bytes, size);
    *value = 0;
    for (i = 0; i < size; i++) {
        *value |= (uint64_t)bytes[i] << (i * 8);
    }
    return result;
}

static MemTxResult bcm2712_outbound(BCM2712PCIeWindow *w, hwaddr offset,
                                    uint64_t *value, unsigned size,
                                    MemTxAttrs attrs, bool write)
{
    BCM2712PCIeState *s = w->host;
    uint64_t addr = w->base + offset;
    unsigned i;

    bcm2712_link_update(s);
    if (!s->link_up) {
        return MEMTX_DECODE_ERROR;
    }
    for (i = 0; i < 4; i++) {
        uint32_t bl = s->regs[(0x4070 + i * 4) / 4];
        uint64_t base_hi = s->regs[(0x4080 + i * 8) / 4] & 0xff;
        uint64_t limit_hi = s->regs[(0x4084 + i * 8) / 4] & 0xff;
        uint64_t base = base_hi << 32 | ((uint64_t)(bl & 0xfff0) << 16);
        uint64_t limit = limit_hi << 32 | (bl & 0xfff00000) | 0xfffff;
        uint64_t pci = (uint64_t)s->regs[(0x4010 + i * 8) / 4] << 32 |
                       s->regs[(0x400c + i * 8) / 4];

        if (limit >= base && addr >= base && addr <= limit &&
            size - 1 <= limit - addr && addr - base <= UINT64_MAX - pci &&
            pci + addr - base <= UINT64_MAX - (size - 1)) {
            return bcm2712_pci_access(&s->pci_as, pci + addr - base,
                                      value, size, attrs, write);
        }
    }
    return MEMTX_DECODE_ERROR;
}

static MemTxResult bcm2712_out_read(void *opaque, hwaddr addr, uint64_t *value,
                                   unsigned size, MemTxAttrs attrs)
{
    *value = UINT64_MAX;
    return bcm2712_outbound(opaque, addr, value, size, attrs, false);
}

static MemTxResult bcm2712_out_write(void *opaque, hwaddr addr, uint64_t value,
                                    unsigned size, MemTxAttrs attrs)
{
    return bcm2712_outbound(opaque, addr, &value, size, attrs, true);
}

static const MemoryRegionOps bcm2712_out_ops = {
    .read_with_attrs = bcm2712_out_read,
    .write_with_attrs = bcm2712_out_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

static MemTxResult bcm2712_inbound(BCM2712PCIeState *s, hwaddr addr,
                                   uint64_t *value, unsigned size,
                                   MemTxAttrs attrs, bool write)
{
    unsigned i;

    bcm2712_link_update(s);
    if (!s->link_up) {
        return MEMTX_DECODE_ERROR;
    }
    for (i = 1; i <= 10; i++) {
        unsigned off = bcm2712_bar_offset(i);
        unsigned remap = bcm2712_remap_offset(i);
        uint64_t base = (uint64_t)s->regs[(off + 4) / 4] << 32 |
                        (s->regs[off / 4] & ~UINT64_C(0x1f));
        uint64_t len = bcm2712_ibar_size(s->regs[off / 4] & 0x1f);
        uint64_t cpu = (uint64_t)s->regs[(remap + 4) / 4] << 32 |
                       (s->regs[remap / 4] & ~UINT64_C(0xfff));
        uint64_t target;
        uint64_t mip = s->controller == 2 ? 0x1000130000ULL : 0x1000131000ULL;

        if (!(s->regs[remap / 4] & 1) || !len || addr < base ||
            size > len || addr - base > len - size ||
            addr - base > UINT64_MAX - cpu) {
            continue;
        }
        target = cpu + addr - base;
        if (s->msi_target && target >= mip && target - mip <= 0x1000 - size) {
            return bcm2712_pci_access(&s->msi_as, target - mip,
                                      value, size, attrs, write);
        }
        /*
         * Only system RAM and the explicitly connected MIP are DMA targets.
         * No recursive CPU->PCI->CPU alias or identity-DMA bypass.
         */
        if (target < s->ram_size && size <= s->ram_size - target) {
            return bcm2712_pci_access(&address_space_memory, target,
                                      value, size, attrs, write);
        }
        return MEMTX_DECODE_ERROR;
    }
    return MEMTX_DECODE_ERROR;
}

static MemTxResult bcm2712_dma_read(void *opaque, hwaddr addr, uint64_t *value,
                                   unsigned size, MemTxAttrs attrs)
{
    *value = UINT64_MAX;
    return bcm2712_inbound(opaque, addr, value, size, attrs, false);
}

static MemTxResult bcm2712_dma_write(void *opaque, hwaddr addr, uint64_t value,
                                    unsigned size, MemTxAttrs attrs)
{
    BCM2712PCIeState *s = opaque;
    MemTxResult result = bcm2712_inbound(s, addr, &value, size, attrs, true);

    /* A notification attempt is not proof that its DMA write was accepted. */
    trace_bcm2712_pcie_dma_write(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                               s->controller, addr, value, size, result);
    return result;
}

static const MemoryRegionOps bcm2712_dma_ops = {
    .read_with_attrs = bcm2712_dma_read,
    .write_with_attrs = bcm2712_dma_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

static AddressSpace *bcm2712_dma_space(PCIBus *bus, void *opaque, int devfn)
{
    return &((BCM2712PCIeState *)opaque)->dma_as;
}

static const PCIIOMMUOps bcm2712_iommu_ops = {
    .get_address_space = bcm2712_dma_space,
};

static bool bcm2712_mdio_supported(BCM2712PCIeState *s)
{
    return s->mdio_reg == 0x1f ||
           (s->mdio_page == 0x1600 && bcm2712_phy_xosc_reg(s->mdio_reg)) ||
           (s->mdio_page == 0x1100 && (s->mdio_reg == 1 || s->mdio_reg == 2));
}

static void bcm2712_mdio_complete(void *opaque)
{
    BCM2712PCIeState *s = opaque;
    uint16_t value = s->regs[0x1104 / 4];

    if (s->mdio_read) {
        if (s->mdio_reg == 0x1f) {
            value = s->mdio_page;
        } else if (s->mdio_page == 0x1600) {
            value = s->phy_xosc[s->mdio_reg];
        } else if (s->mdio_reg == 1) {
            /* Logical PLL/SSC state, not an analog PHY/timing claim. */
            value = bcm2712_refclk54(s) ? 0x800 : 0;
            if (value && (s->phy_ssc[2] & 0xc000) == 0xc000) {
                value |= 0x400;
            }
        } else {
            value = s->phy_ssc[2];
        }
        s->regs[0x1108 / 4] = BIT(31) | value;
    } else {
        if (s->mdio_reg == 0x1f) {
            s->mdio_page = value;
        } else if (s->mdio_page == 0x1600) {
            s->phy_xosc[s->mdio_reg] = value;
        } else {
            s->phy_ssc[2] = value;
        }
        s->regs[0x1104 / 4] &= ~BIT(31);
    }
    s->mdio_busy = s->mdio_armed = false;
    bcm2712_link_update(s);
}

static void bcm2712_mdio_start(BCM2712PCIeState *s)
{
    s->mdio_busy = true;
    if (!bcm2712_mdio_supported(s) ||
        (!s->mdio_read && s->mdio_reg == 0x1f &&
         s->regs[0x1104 / 4] != (BIT(31) | 0x1600) &&
         s->regs[0x1104 / 4] != (BIT(31) | 0x1100)) ||
        (!s->mdio_read && s->mdio_page == 0x1100 && s->mdio_reg == 1)) {
        qemu_log_mask(LOG_UNIMP,
                      "bcm2712-pcie%u: unsupported MDIO page=%x reg=%x\n",
                      s->controller, s->mdio_page, s->mdio_reg);
        return; /* observable timeout, cleared only by reset */
    }
    timer_mod(s->mdio_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 1000);
}

static bool bcm2712_pcie_latch(hwaddr off)
{
    switch (off) {
    case 0x188: /* inbound endianness */
    case 0x43c: /* private class code */
    case 0x4dc: /* link capability descriptor */
    case 0x1100: /* MDIO address */
    case 0x1104: /* MDIO write data */
    case 0x1108: /* MDIO read data */
    case 0x184c: /* PM clock period */
    case 0x1804: /* PHY control descriptor, no physical effect */
    case 0x4008: /* SCB control */
    case 0x4064: /* PERSTB, no link without PHY */
    case 0x4304: /* hard debug */
    case 0x9000: /* downstream configuration index */
    case 0x9210: /* bridge software init */
        return true;
    default:
        /* Outbound/inbound address descriptors used before post_setup. */
        return (off >= 0x400c && off <= 0x4040) ||
               (off >= 0x4070 && off <= 0x409c) ||
               (off >= 0x40ac && off <= 0x4170);
    }
}

static uint64_t bcm2712_pcie_read(void *opaque, hwaddr off, unsigned size)
{
    BCM2712PCIeState *s = opaque;
    uint32_t value = 0;

    if (off < 0x1000 && !bcm2712_pcie_latch(off)) {
        value = pci_host_config_read_common(s->root_port, off, 4096, size);
        if (off <= 0xbf && off + size > 0xbe) {
            unsigned i;
            uint16_t status;

            bcm2712_link_update(s);
            status = s->link_up ? PCI_EXP_LNKSTA_DLLLA | 0x42 : 0;
            for (i = 0; i < size; i++) {
                if (off + i == 0xbe || off + i == 0xbf) {
                    value = (value & ~(0xffU << (8 * i))) |
                            (((status >> (8 * (off + i - 0xbe))) & 0xff) <<
                             (8 * i));
                }
            }
        }
    } else if (off == 0x4068) {
        bcm2712_link_update(s);
        value = s->link_up ? 0xb0 : 0x80; /* RC mode plus logical link state. */
    } else if (off >= 0x8000 && off < 0x9000) {
        PCIDevice *dev = bcm2712_config_device(s);

        value = dev ? pci_host_config_read_common(dev, off - 0x8000,
                                                  4096, size) : UINT32_MAX;
    } else if (bcm2712_pcie_latch(off)) {
        value = s->regs[off / 4];
    } else {
        qemu_log_mask(LOG_UNIMP, "bcm2712-pcie%u: unsupported read @0x%"
                      HWADDR_PRIx "\n", s->controller, off);
    }
    trace_bcm2712_pcie_access(s->controller, false, off, value);
    return value;
}

static void bcm2712_pcie_write(void *opaque, hwaddr off, uint64_t value,
                               unsigned size)
{
    BCM2712PCIeState *s = opaque;

    trace_bcm2712_pcie_access(s->controller, true, off, value);
    if (off < 0x1000 && !bcm2712_pcie_latch(off)) {
        pci_host_config_write_common(s->root_port, off, 4096, value, size);
        bcm2712_link_update(s);
        return;
    }
    if (off >= 0x8000 && off < 0x9000) {
        PCIDevice *dev = bcm2712_config_device(s);

        if (dev) {
            pci_host_config_write_common(dev, off - 0x8000, 4096, value, size);
        }
        return;
    }
    if (off == 0x1100) {
        if (s->mdio_busy) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "bcm2712-pcie: MDIO command while busy\n");
            return;
        }
        s->regs[off / 4] = value;
        s->mdio_reg = value & 0x1f;
        s->mdio_read = value & BIT(20);
        s->mdio_armed = !(value & ~(BIT(20) | 0x1f)); /* only port0 */
        if (s->mdio_read) {
            s->regs[0x1108 / 4] = 0;
            if (s->mdio_armed) {
                bcm2712_mdio_start(s);
            } else {
                s->mdio_busy = true;
            }
        }
        return;
    }
    if (off == 0x1104) {
        if (s->mdio_busy) {
            return;
        }
        s->regs[off / 4] = value;
        if ((value & BIT(31)) && s->mdio_armed && !s->mdio_read) {
            bcm2712_mdio_start(s);
        } else if (value & BIT(31)) {
            s->mdio_busy = true;
            qemu_log_mask(LOG_UNIMP,
                          "bcm2712-pcie: invalid MDIO write request\n");
        }
        return;
    }
    if (off == 0x1108) {
        return; /* read data/completion is read-only */
    }
    if (bcm2712_pcie_latch(off)) {
        s->regs[off / 4] = value;
        bcm2712_link_update(s);
        if ((off == 0x9210 && (value & 2)) ||
            (off == 0x4064 && !(value & 4))) {
            if (s->endpoint) {
                pci_device_reset(s->endpoint);
            }
        }
    } else {
        qemu_log_mask(LOG_UNIMP, "bcm2712-pcie%u: unsupported write @0x%"
                      HWADDR_PRIx " = 0x%" PRIx64 "\n",
                      s->controller, off, value);
    }
}

static const MemoryRegionOps bcm2712_pcie_ops = {
    .read = bcm2712_pcie_read,
    .write = bcm2712_pcie_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 4 },
    .impl = { .min_access_size = 1, .max_access_size = 4 },
};

static void bcm2712_pcie_reset(DeviceState *dev)
{
    BCM2712PCIeState *s = BCM2712_PCIE(dev);

    memset(s->regs, 0, sizeof(s->regs));
    timer_del(s->mdio_timer);
    timer_del(s->link_timer);
    s->link_up = false;
    memset(s->phy_xosc, 0, sizeof(s->phy_xosc));
    memset(s->phy_ssc, 0, sizeof(s->phy_ssc));
    s->mdio_page = s->mdio_reg = 0;
    s->mdio_busy = s->mdio_armed = s->mdio_read = false;
    s->regs[0x9210 / 4] = 2; /* bridge held in reset */
    s->regs[0x4dc / 4] = (s->controller == 2 ? 4 : 1) << 4;
}

static void bcm2712_pcie_init(Object *obj)
{
    BCM2712PCIeState *s = BCM2712_PCIE(obj);

    memory_region_init_io(&s->mmio, obj, &bcm2712_pcie_ops, s,
                          "bcm2712-pcie-probe", 0x9310);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->mmio);
    s->mdio_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, bcm2712_mdio_complete, s);
    s->link_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, bcm2712_link_complete, s);
}

static void bcm2712_pcie_finalize(Object *obj)
{
    timer_free(BCM2712_PCIE(obj)->mdio_timer);
    timer_free(BCM2712_PCIE(obj)->link_timer);
}

static const Property bcm2712_pcie_properties[] = {
    DEFINE_PROP_UINT32("controller", BCM2712PCIeState, controller, 2),
    DEFINE_PROP_BOOL("rp1-gpio-lab", BCM2712PCIeState, rp1_gpio_lab, false),
    DEFINE_PROP_BOOL("connect-rp1", BCM2712PCIeState, connect_rp1, false),
    DEFINE_PROP_UINT64("ram-size", BCM2712PCIeState, ram_size, 0),
    DEFINE_PROP_LINK("msi-target", BCM2712PCIeState, msi_target,
                     TYPE_MEMORY_REGION, MemoryRegion *),
};

static void bcm2712_intx(void *opaque, int pin, int level)
{
    BCM2712PCIeState *s = opaque;

    qemu_set_irq(s->intx[pin], level);
}

static int bcm2712_map_irq(PCIDevice *dev, int pin)
{
    return (PCI_SLOT(dev->devfn) + pin) % 4;
}

static void bcm2712_pcie_realize(DeviceState *dev, Error **errp)
{
    BCM2712PCIeState *s = BCM2712_PCIE(dev);
    PCIHostState *host = PCI_HOST_BRIDGE(s);
    unsigned i;

    memory_region_init(&s->pci_mem, OBJECT(s), "bcm2712-pci-memory",
                       UINT64_MAX);
    memory_region_init(&s->pci_io, OBJECT(s), "bcm2712-pci-io", 65536);
    for (i = 0; i < 4; i++) {
        sysbus_init_irq(SYS_BUS_DEVICE(s), &s->intx[i]);
    }
    host->bus = pci_register_root_bus(dev, s->controller == 2 ?
        "bcm2712-rp1-root" : "bcm2712-expansion-root", bcm2712_intx,
        bcm2712_map_irq, s, &s->pci_mem, &s->pci_io, 0, 4, TYPE_PCIE_BUS);
    address_space_init(&s->pci_as, &s->pci_mem, "bcm2712-pci-mmio");
    memory_region_init_io(&s->dma_root, OBJECT(s), &bcm2712_dma_ops, s,
                          "bcm2712-inbound", UINT64_MAX);
    address_space_init(&s->dma_as, &s->dma_root, "bcm2712-dma");
    if (s->msi_target) {
        address_space_init(&s->msi_as, s->msi_target, "bcm2712-msi-target");
    }
    pci_setup_iommu(host->bus, &bcm2712_iommu_ops, s);
    for (i = 0; i < 2; i++) {
        BCM2712PCIeWindow *w = &s->outbound[i];

        w->host = s;
        w->base = s->controller == 2 ?
                  (i ? 0x1c00000000ULL : 0x1f00000000ULL) :
                  (i ? 0x1800000000ULL : 0x1b80000000ULL);
        w->size = s->controller == 2 ?
                  (i ? 0x300000000ULL : 0xfffffffcULL) :
                  (i ? 0x380000000ULL : 0x80000000ULL);
        memory_region_init_io(&w->mr, OBJECT(s), &bcm2712_out_ops, w,
                              "bcm2712-outbound", w->size);
        /*
         * This aperture forwards into PCI. An endpoint event can synchronously
         * issue MSI through our inbound region. Only the forwarding aperture
         * is reentrancy-safe; inbound destinations exclude this aperture.
         */
        w->mr.disable_reentrancy_guard = true;
        sysbus_init_mmio(SYS_BUS_DEVICE(s), &w->mr);
    }
    s->root_port = pci_new(0, "bcm2712-root-port");
    object_property_add_child(OBJECT(s), "root-port", OBJECT(s->root_port));
    qdev_prop_set_uint8(DEVICE(s->root_port), "chassis", s->controller);
    PCIE_SLOT(s->root_port)->speed = QEMU_PCI_EXP_LNK_5GT;
    PCIE_SLOT(s->root_port)->width = s->controller == 2 ?
                                   QEMU_PCI_EXP_LNK_X4 : QEMU_PCI_EXP_LNK_X1;
    if (!pci_realize_and_unref(s->root_port, host->bus, errp)) {
        return;
    }
    /*
     * The generic root-port helper only exposes CCC/ES by default. This
     * host also implements Link Disable through its logical state machine.
     */
    s->root_port->wmask[s->root_port->exp.exp_cap + PCI_EXP_LNKCTL] |=
        PCI_EXP_LNKCTL_LD;
    if (s->connect_rp1) {
        s->endpoint = pci_new(0, "rp1-pci");
        object_property_add_child(OBJECT(s), "rp1", OBJECT(s->endpoint));
        qdev_prop_set_bit(DEVICE(s->endpoint), "native-clock", true);
        qdev_prop_set_bit(DEVICE(s->endpoint), "gpio-lab", s->rp1_gpio_lab);
        pci_realize_and_unref(s->endpoint,
            pci_bridge_get_sec_bus(PCI_BRIDGE(s->root_port)), errp);
    }
}

static const char *bcm2712_root_path(PCIHostState *host, PCIBus *bus)
{
    return BCM2712_PCIE(host)->controller == 2 ? "0002:00" : "0001:00";
}

static void bcm2712_root_class_init(ObjectClass *oc, const void *data)
{
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(oc);
    PCIERootPortClass *rpc = PCIE_ROOT_PORT_CLASS(oc);

    pc->vendor_id = 0x14e4;
    pc->device_id = 0x2712;
    pc->revision = 0x20;
    rpc->exp_offset = 0xac;
    rpc->aer_offset = 0x100;
    DEVICE_CLASS(oc)->user_creatable = false;
}

static const TypeInfo bcm2712_root_type = {
    .name = "bcm2712-root-port",
    .parent = TYPE_PCIE_ROOT_PORT,
    .instance_size = sizeof(PCIESlot),
    .class_init = bcm2712_root_class_init,
};

static const VMStateDescription bcm2712_pcie_vmstate = {
    .name = TYPE_BCM2712_PCIE,
    .unmigratable = true,
};

static void bcm2712_pcie_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = bcm2712_pcie_realize;
    PCI_HOST_BRIDGE_CLASS(oc)->root_bus_path = bcm2712_root_path;
    device_class_set_props(dc, bcm2712_pcie_properties);
    device_class_set_legacy_reset(dc, bcm2712_pcie_reset);
    dc->vmsd = &bcm2712_pcie_vmstate;
    dc->user_creatable = false;
    dc->desc = "BCM2712 PCIe logical link, indexed config and address windows";
}

static const TypeInfo bcm2712_pcie_type = {
    .name = TYPE_BCM2712_PCIE,
    .parent = TYPE_PCI_HOST_BRIDGE,
    .instance_size = sizeof(BCM2712PCIeState),
    .instance_init = bcm2712_pcie_init,
    .instance_finalize = bcm2712_pcie_finalize,
    .class_init = bcm2712_pcie_class_init,
};

static void bcm2712_pcie_register(void)
{
    type_register_static(&bcm2712_root_type);
    type_register_static(&bcm2712_pcie_type);
}
type_init(bcm2712_pcie_register)

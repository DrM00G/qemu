/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Experimental RP1 PCIe endpoint, SPI0-only local research subset.
 * AI-assisted; not intended for upstream submission.
 * Sources: Raspberry Pi RP1 datasheet sections 2.3 and 3.6;
 * raspberrypi/linux drivers/mfd/rp1.c, include/dt-bindings/mfd/rp1.h,
 * include/linux/rp1_platform.h. See experiments/cm5-phase5/README.md.
 */
#include "qemu/osdep.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_device.h"
#include "hw/pci/pcie.h"
#include "hw/pci/msix.h"
#include "hw/ssi/dw-apb-ssi.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/units.h"
#include "qapi/error.h"
#include "trace.h"

#define TYPE_RP1_PCI "rp1-pci"
OBJECT_DECLARE_SIMPLE_TYPE(RP1PCIState, RP1_PCI)

#define RP1_SPI0 0x50000
#define RP1_PCIE_APBS 0x108000
#define RP1_SPI0_IRQ 19
#define RP1_VECTORS 61

struct RP1PCIState {
    PCIDevice parent_obj;
    MemoryRegion bar0, bar1, bar2;
    DWAPBSSIState spi;
    uint32_t irq_cfg[RP1_VECTORS];
    bool native_clock;
    uint32_t clocks[0x10038 / 4];
    uint64_t irq_level;
    uint64_t irq_outstanding;
};

/*
 * Limited clock-manager state used by clk-rp1's real SYS/SLOW/PLL paths.
 * Reset presets are a documented lab boot state, not captured firmware.
 */
static bool rp1_clock_reg(hwaddr addr)
{
    return (addr >= 0x18014 && addr <= 0x18030 && !(addr & 3)) ||
           ((addr >= 0x20000 && addr <= 0x20014) ||
            (addr >= 0x24000 && addr <= 0x24018) ||
            (addr >= 0x28000 && addr <= 0x28014));
}

static bool rp1_pll_locked(RP1PCIState *s, unsigned base)
{
    uint32_t *r = &s->clocks[(base - 0x18000) / 4];

    return (r[0] & 0x3f) == 1 && !(r[1] & 0x29) &&
           r[2] >= 16 && r[2] <= 320;
}

static void rp1_clock_update(RP1PCIState *s)
{
    uint32_t ctrl = s->clocks[0x14 / 4];
    unsigned src = ctrl & 3;
    uint64_t hz = 0;

    if (ctrl & BIT(11)) {
        if (src == 0) {
            hz = 50000000;
        } else if (src == 2 && rp1_pll_locked(s, 0x20000)) {
            uint32_t prim = s->clocks[0x8010 / 4];
            unsigned d1 = (prim >> 16) & 7, d2 = (prim >> 12) & 7;

            if (d1 && d2) {
                uint64_t fb = ((uint64_t)s->clocks[0x8008 / 4] << 24) |
                              s->clocks[0x800c / 4];
                hz = ((50000000 * fb) >> 24) / d1 / d2;
            }
        }
    }
    if (hz) {
        unsigned div = s->clocks[0x18 / 4];
        hz /= div ? div : 65536;
    }
    dw_apb_ssi_set_frequency(&s->spi, hz);
}

static uint32_t rp1_clock_read(RP1PCIState *s, hwaddr addr)
{
    uint32_t value = s->clocks[(addr - 0x18000) / 4];

    if (addr == 0x20000 || addr == 0x24000 || addr == 0x28000) {
        value &= ~BIT(31);
        if (rp1_pll_locked(s, addr)) {
            value |= BIT(31);
        }
    } else if (addr == 0x18020 || addr == 0x18030) {
        uint32_t ctrl = s->clocks[(addr - 0x18000 - 12) / 4];
        unsigned src = ctrl & 3;

        value = (ctrl & BIT(11)) && (src == 0 ||
                 (src == 2 && rp1_pll_locked(s, 0x20000))) ? BIT(src) : 0;
    }
    return value;
}

static void rp1_clock_write(RP1PCIState *s, hwaddr addr, uint32_t value)
{
    if (addr == 0x18020 || addr == 0x18030) {
        return; /* active-parent status is read-only */
    }
    if (addr == 0x20000 || addr == 0x24000 || addr == 0x28000) {
        value &= 0x3f; /* lock is derived, not writable */
    }
    s->clocks[(addr - 0x18000) / 4] = value;
    rp1_clock_update(s);
}

static void rp1_irq_update(RP1PCIState *s, unsigned vector)
{
    uint64_t bit = UINT64_C(1) << vector;

    if ((s->irq_level & bit) && (s->irq_cfg[vector] & BIT(0)) &&
        !(s->irq_outstanding & bit) && msix_enabled(PCI_DEVICE(s))) {
        if (s->irq_cfg[vector] & BIT(3)) {
            s->irq_outstanding |= bit;
        }
        trace_rp1_msix(vector);
        msix_notify(PCI_DEVICE(s), vector);
    }
}

static void rp1_spi_irq(void *opaque, int n, int level)
{
    RP1PCIState *s = opaque;
    uint64_t bit = UINT64_C(1) << RP1_SPI0_IRQ;
    bool previous = !!(s->irq_level & bit);

    if (level) {
        s->irq_level |= bit;
        if (!previous) {
            rp1_irq_update(s, RP1_SPI0_IRQ);
        }
    } else {
        s->irq_level &= ~bit;
    }
}

static uint64_t rp1_read(void *opaque, hwaddr addr, unsigned size)
{
    RP1PCIState *s = opaque;
    hwaddr off;

    if (s->native_clock && rp1_clock_reg(addr)) {
        return rp1_clock_read(s, addr);
    }
    switch (addr) {
    case 0:
        return 0x20001927; /* RP1_C0_CHIP_ID, Linux rp1_platform.h */
    case 4:
        return BIT(1); /* RP1_PLATFORM_ASIC */
    case RP1_PCIE_APBS + 0x108:
        return s->irq_level;
    case RP1_PCIE_APBS + 0x10c:
        return s->irq_level >> 32;
    }
    off = addr - RP1_PCIE_APBS;
    if (addr >= RP1_PCIE_APBS && off >= 8 &&
        off < 8 + RP1_VECTORS * 4) {
        return s->irq_cfg[(off - 8) / 4];
    }
    qemu_log_mask(LOG_UNIMP, "rp1: unimplemented read @0x%" HWADDR_PRIx
                  "\n", addr);
    return 0;
}

static void rp1_write(void *opaque, hwaddr addr, uint64_t val,
                       unsigned size)
{
    RP1PCIState *s = opaque;
    hwaddr off = addr - RP1_PCIE_APBS;
    unsigned alias = off & 0xc00;
    unsigned reg = off & ~0xc00;

    if (s->native_clock && rp1_clock_reg(addr)) {
        rp1_clock_write(s, addr, val);
        return;
    }
    if (addr >= RP1_PCIE_APBS && off < 0x1000 && reg >= 8 &&
        reg < 8 + RP1_VECTORS * 4 && alias != 0x400) {
        unsigned vector = (reg - 8) / 4;
        uint32_t *cfg = &s->irq_cfg[vector];

        if (alias == 0x800) {
            *cfg |= val & 9;
        } else if (alias == 0xc00) {
            *cfg &= ~(val & 9);
        } else {
            *cfg = val & 9;
        }
        if ((val & BIT(2)) && alias != 0xc00) {
            s->irq_outstanding &= ~(UINT64_C(1) << vector);
        }
        rp1_irq_update(s, vector);
        if ((val & BIT(1)) && alias != 0xc00 &&
            (*cfg & BIT(0)) && msix_enabled(PCI_DEVICE(s))) {
            msix_notify(PCI_DEVICE(s), vector);
        }
        return;
    }
    qemu_log_mask(LOG_UNIMP, "rp1: unimplemented write @0x%" HWADDR_PRIx
                  " = 0x%" PRIx64 "\n", addr, val);
}

static const MemoryRegionOps rp1_ops = {
    .read = rp1_read,
    .write = rp1_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void rp1_config_write(PCIDevice *pdev, uint32_t addr,
                              uint32_t val, int len)
{
    RP1PCIState *s = RP1_PCI(pdev);
    unsigned i;

    pci_default_write_config(pdev, addr, val, len);
    for (i = 0; i < RP1_VECTORS; i++) {
        rp1_irq_update(s, i);
    }
}

static void rp1_realize(PCIDevice *pdev, Error **errp)
{
    RP1PCIState *s = RP1_PCI(pdev);
    unsigned i;

    /*
     * Aperture sizes agree with RP1 boot logs in raspberrypi/linux #6656.
     * MSI-X table placement is experimental, not a physical config dump.
     * BAR2 is a plain research scratchpad, not RP1 firmware shared-memory
     * protocol emulation. Its zero-on-reset policy is a lab convention.
     */
    memory_region_init(&s->bar0, OBJECT(s), "rp1-bar0", 16 * KiB);
    memory_region_init_io(&s->bar1, OBJECT(s), &rp1_ops, s,
                          "rp1-peripherals", 4 * MiB);
    if (!memory_region_init_ram(&s->bar2, OBJECT(s), "rp1-bar2", 64 * KiB,
                                errp)) {
        return;
    }
    pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->bar0);
    pci_register_bar(pdev, 1, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->bar1);
    pci_register_bar(pdev, 2, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->bar2);
    if (pcie_endpoint_cap_init(pdev, 0x70) < 0) {
        error_setg(errp, "rp1: could not create PCI Express capability");
        return;
    }
    pcie_cap_fill_link_ep_usp(pdev, QEMU_PCI_EXP_LNK_X4,
                              QEMU_PCI_EXP_LNK_5GT, false);
    if (msix_init(pdev, RP1_VECTORS, &s->bar0, 0, 0,
                  &s->bar0, 0, 0x1000, 0xb0, errp)) {
        pcie_cap_exit(pdev);
        return;
    }
    for (i = 0; i < RP1_VECTORS; i++) {
        msix_vector_use(pdev, i);
    }
    if (!qdev_realize(DEVICE(&s->spi), NULL, errp)) {
        msix_uninit(pdev, &s->bar0, &s->bar0);
        pcie_cap_exit(pdev);
        return;
    }
    memory_region_add_subregion(&s->bar1, RP1_SPI0, &s->spi.mmio);
    qdev_connect_gpio_out(DEVICE(&s->spi), 0,
                          qdev_get_gpio_in(DEVICE(s), 0));
}

static void rp1_exit(PCIDevice *pdev)
{
    RP1PCIState *s = RP1_PCI(pdev);

    device_cold_reset(DEVICE(&s->spi));
    memory_region_del_subregion(&s->bar1, &s->spi.mmio);
    qdev_unrealize(DEVICE(&s->spi));
    msix_uninit(pdev, &s->bar0, &s->bar0);
    pcie_cap_exit(pdev);
}

static void rp1_reset(DeviceState *dev)
{
    RP1PCIState *s = RP1_PCI(dev);

    memset(s->irq_cfg, 0, sizeof(s->irq_cfg));
    s->irq_level = s->irq_outstanding = 0;
    memset(memory_region_get_ram_ptr(&s->bar2), 0, 64 * KiB);
    memory_region_set_dirty(&s->bar2, 0, 64 * KiB);
    msix_reset(PCI_DEVICE(s));
    device_cold_reset(DEVICE(&s->spi));
    if (s->native_clock) {
        unsigned bank;

        memset(s->clocks, 0, sizeof(s->clocks));
        for (bank = 0x8000; bank <= 0x10000; bank += 0x4000) {
            s->clocks[bank / 4] = 1;
            s->clocks[(bank + 8) / 4] = 20;
            s->clocks[(bank + 0x10) / 4] = (5 << 16) | (1 << 12);
            s->clocks[(bank + 0x14) / 4] = BIT(31) | (8 << 8);
        }
        s->clocks[0x14 / 4] = BIT(11) | 2;
        s->clocks[0x18 / 4] = 1;
        s->clocks[0x24 / 4] = BIT(11);
        s->clocks[0x28 / 4] = 1;
        rp1_clock_update(s);
    }
}

static void rp1_init(Object *obj)
{
    RP1PCIState *s = RP1_PCI(obj);

    object_initialize_child(obj, "spi0", &s->spi, TYPE_DW_APB_SSI);
    s->spi.bus = ssi_create_bus(DEVICE(obj), "spi");
    qdev_init_gpio_in(DEVICE(obj), rp1_spi_irq, 1);
}

static const VMStateDescription rp1_vmstate = {
    .name = TYPE_RP1_PCI,
    .unmigratable = 1,
};

static const Property rp1_properties[] = {
    DEFINE_PROP_BOOL("native-clock", RP1PCIState, native_clock, false),
};

static void rp1_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);

    pc->realize = rp1_realize;
    pc->exit = rp1_exit;
    pc->config_write = rp1_config_write;
    pc->vendor_id = 0x1de4;
    pc->device_id = 0x0001;
    pc->revision = 2;
    pc->class_id = PCI_CLASS_OTHERS;
    dc->desc = "Experimental RP1 PCIe endpoint (SPI0 PIO research subset)";
    dc->vmsd = &rp1_vmstate;
    device_class_set_props(dc, rp1_properties);
    device_class_set_legacy_reset(dc, rp1_reset);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo rp1_type = {
    .name = TYPE_RP1_PCI,
    .parent = TYPE_PCI_DEVICE,
    .instance_size = sizeof(RP1PCIState),
    .instance_init = rp1_init,
    .class_init = rp1_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_PCIE_DEVICE },
        { },
    },
};

static void rp1_register_types(void)
{
    type_register_static(&rp1_type);
}
type_init(rp1_register_types)

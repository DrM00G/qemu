/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * CM5 + official CM5 I/O Board development platform, local research only.
 * AI-assisted; not for upstream submission.
 *
 * Independent MachineState implementation: not a virt subclass. CPU affinity,
 * low RAM, GICv2 and UART10 mapping follow public BCM2712 Linux DT sources.
 * GPEX, GICv2m, header UART, PL031 and VirtIO are explicit substitutes.
 * Neither physical firmware boot nor complete BCM2712 compatibility is claimed.
 */
#include "qemu/osdep.h"
#include "hw/arm/cm5io-dev.h"
#include "hw/arm/bcm2712-pcie.h"
#include "hw/arm/boot.h"
#include "hw/core/boards.h"
#include "hw/core/qdev-properties.h"
#include "hw/char/pl011.h"
#include "hw/pci-host/gpex.h"
#include "hw/pci/pci.h"
#include "hw/ssi/ssi.h"
#include "hw/intc/bcm2712-mip.h"
#include "hw/sd/bcm2712-sdhci.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/units.h"
#include "qemu/module.h"
#include "system/device_tree.h"
#include "system/system.h"
#include "system/tcg.h"
#include "system/qtest.h"
#include "target/arm/cpu.h"
#include "target/arm/gtimer.h"
#include <libfdt.h>

#define TYPE_CM5IO_DEV MACHINE_TYPE_NAME("cm5io-dev")
OBJECT_DECLARE_SIMPLE_TYPE(CM5IODevState, CM5IO_DEV)

struct CM5IODevState {
    MachineState parent_obj;
    struct arm_boot_info bootinfo;
    DeviceState *gic;
    MemoryRegion ecam[2], pci_mmio[2];
    uint32_t gic_phandle, msi_phandle, clk_phandle;
    uint32_t mip_phandle[2];
    DeviceState *mip[2];
    MemoryRegion dma_root[2], dma_identity[2], dma_msi[2];
    AddressSpace dma_as[2];
    bool native_mip;
    bool native_emmc;
    bool emmc_dma;
    bool native_pcie;
    bool rp1_gpio_lab;
    int fdt_size;
    uint32_t gpio_vref;
    bool header_spi, header_uart, expansion, test_rtc;
};

static void cm5_reg(void *fdt, const char *node, uint64_t addr, uint64_t size)
{
    qemu_fdt_setprop_sized_cells(fdt, node, "reg", 2, addr, 2, size);
}

static void cm5_clock(CM5IODevState *s, const char *node,
                       uint32_t rate, uint32_t phandle)
{
    void *fdt = MACHINE(s)->fdt;

    qemu_fdt_add_subnode(fdt, node);
    qemu_fdt_setprop_string(fdt, node, "compatible", "fixed-clock");
    qemu_fdt_setprop_cell(fdt, node, "#clock-cells", 0);
    qemu_fdt_setprop_cell(fdt, node, "clock-frequency", rate);
    qemu_fdt_setprop_cell(fdt, node, "phandle", phandle);
}

static void cm5_uart(CM5IODevState *s, const char *node, hwaddr addr,
                     unsigned irq, Chardev *chr, bool console)
{
    void *fdt = MACHINE(s)->fdt;
    const char compat[] = "arm,pl011\0arm,primecell";
    const char names[] = "uartclk\0apb_pclk";

    pl011_create(addr, qdev_get_gpio_in(s->gic, irq), chr);
    qemu_fdt_add_subnode(fdt, node);
    qemu_fdt_setprop(fdt, node, "compatible", compat, sizeof(compat));
    cm5_reg(fdt, node, addr, 0x1000);
    qemu_fdt_setprop_cells(fdt, node, "interrupts", 0, irq, 4);
    qemu_fdt_setprop_cells(fdt, node, "clocks", s->clk_phandle,
                            s->clk_phandle);
    qemu_fdt_setprop(fdt, node, "clock-names", names, sizeof(names));
    if (console) {
        qemu_fdt_setprop_string(fdt, "/chosen", "stdout-path", node);
        qemu_fdt_setprop_string(fdt, "/aliases", "serial0", node);
    } else {
        qemu_fdt_setprop_string(fdt, "/aliases", "serial1", node);
        qemu_fdt_setprop_string(fdt, node, "qemu,substitute-for",
                                "RP1 UART0 on GPIO14/15, header pins 8/10");
    }
}

static void cm5_cpus_gic(CM5IODevState *s)
{
    MachineState *ms = MACHINE(s);
    void *fdt = ms->fdt;
    unsigned ncpu = ms->smp.cpus;
    unsigned i;
    const int timer_irqs[] = { 30, 27, 26, 29 };
    DeviceState *gic;

    qemu_fdt_add_subnode(fdt, "/cpus");
    qemu_fdt_setprop_cell(fdt, "/cpus", "#address-cells", 2);
    qemu_fdt_setprop_cell(fdt, "/cpus", "#size-cells", 0);
    for (i = 0; i < ncpu; i++) {
        Object *cpu = object_new(ms->cpu_type);
        g_autofree char *node = g_strdup_printf("/cpus/cpu@%x", i << 8);

        /* BCM2712 DT uses MPIDR 0x000, 0x100, 0x200, 0x300. */
        object_property_set_int(cpu, "mp-affinity", i << 8, &error_fatal);
        object_property_set_bool(cpu, "has_el3", false, &error_fatal);
        object_property_set_bool(cpu, "has_el2", true, &error_fatal);
        object_property_set_int(cpu, "cntfrq", 54000000, &error_fatal);
        object_property_set_bool(cpu, "start-powered-off", i != 0,
                                  &error_fatal);
        object_property_set_int(cpu, "psci-conduit", QEMU_PSCI_CONDUIT_SMC,
                                &error_fatal);
        qdev_realize(DEVICE(cpu), NULL, &error_fatal);
        object_unref(cpu);
        qemu_fdt_add_subnode(fdt, node);
        qemu_fdt_setprop_string(fdt, node, "device_type", "cpu");
        qemu_fdt_setprop_string(fdt, node, "compatible", "arm,cortex-a76");
        qemu_fdt_setprop_cells(fdt, node, "reg", 0, i << 8);
        qemu_fdt_setprop_string(fdt, node, "enable-method", "psci");
    }
    s->gic = gic = qdev_new("arm_gic");
    qdev_prop_set_uint32(gic, "revision", 2);
    qdev_prop_set_uint32(gic, "num-cpu", ncpu);
    qdev_prop_set_uint32(gic, "num-irq", CM5_EXTERNAL_IRQS + 32);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(gic), &error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(gic), 0, CM5_GIC_DIST);
    sysbus_mmio_map(SYS_BUS_DEVICE(gic), 1, CM5_GIC_CPU);
    for (i = 0; i < ncpu; i++) {
        DeviceState *cpu = DEVICE(qemu_get_cpu(i));
        unsigned j;

        for (j = 0; j < ARRAY_SIZE(timer_irqs); j++) {
            qdev_connect_gpio_out(cpu, j, qdev_get_gpio_in(gic,
                CM5_EXTERNAL_IRQS + i * 32 + timer_irqs[j]));
        }
        for (j = 0; j < 4; j++) {
            sysbus_connect_irq(SYS_BUS_DEVICE(gic), i + j * ncpu,
                                qdev_get_gpio_in(cpu, ARM_CPU_IRQ + j));
        }
    }
    qemu_fdt_add_subnode(fdt, "/interrupt-controller@107fff9000");
    qemu_fdt_setprop_string(fdt, "/interrupt-controller@107fff9000",
                            "compatible", "arm,gic-400");
    qemu_fdt_setprop_cells(fdt, "/interrupt-controller@107fff9000", "reg",
        0x10, 0x7fff9000, 0, 0x1000, 0x10, 0x7fffa000, 0, 0x2000);
    qemu_fdt_setprop(fdt, "/interrupt-controller@107fff9000",
                     "interrupt-controller", NULL, 0);
    qemu_fdt_setprop_cell(fdt, "/interrupt-controller@107fff9000",
                          "#interrupt-cells", 3);
    qemu_fdt_setprop_cell(fdt, "/interrupt-controller@107fff9000",
                          "#address-cells", 2);
    qemu_fdt_setprop_cell(fdt, "/interrupt-controller@107fff9000",
                          "#size-cells", 2);
    qemu_fdt_setprop(fdt, "/interrupt-controller@107fff9000",
                     "ranges", NULL, 0);
    qemu_fdt_setprop_cell(fdt, "/interrupt-controller@107fff9000",
                          "phandle", s->gic_phandle);
    qemu_fdt_setprop_cell(fdt, "/", "interrupt-parent", s->gic_phandle);

    qemu_fdt_add_subnode(fdt, "/timer");
    qemu_fdt_setprop_string(fdt, "/timer", "compatible", "arm,armv8-timer");
    qemu_fdt_setprop_cells(fdt, "/timer", "interrupts",
        1, 13, 0xf08, 1, 14, 0xf08, 1, 11, 0xf08, 1, 10, 0xf08);
    qemu_fdt_add_subnode(fdt, "/psci");
    qemu_fdt_setprop_string(fdt, "/psci", "compatible", "arm,psci-0.2");
    qemu_fdt_setprop_string(fdt, "/psci", "method", "smc");
}

static void cm5_native_mip(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    unsigned n, i;

    for (n = 0; n < 2; n++) {
        hwaddr base = n ? CM5_MIP1 : CM5_MIP0;
        unsigned first = n ? 8 : 0;
        unsigned count = n ? 8 : 64;
        unsigned spi_base = n ? 247 : 128;
        g_autofree char *node =
            g_strdup_printf("/msi-controller@%" HWADDR_PRIx, base);
        DeviceState *dev = qdev_new(TYPE_BCM2712_MIP);

        s->mip[n] = dev;
        s->mip_phandle[n] = qemu_fdt_alloc_phandle(fdt);
        object_property_add_child(OBJECT(s), n ? "mip1" : "mip0", OBJECT(dev));
        qdev_prop_set_uint32(dev, "first-vector", first);
        qdev_prop_set_uint32(dev, "num-vectors", count);
        sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
        sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, base);
        for (i = 0; i < count; i++) {
            /* Linux mip_middle_domain_alloc: GIC SPI = base + MSI data. */
            sysbus_connect_irq(SYS_BUS_DEVICE(dev), i,
                               qdev_get_gpio_in(s->gic, spi_base + first + i));
        }
        qemu_fdt_add_subnode(fdt, node);
        qemu_fdt_setprop_string(fdt, node, "compatible", "brcm,bcm2712-mip");
        qemu_fdt_setprop_sized_cells(fdt, node, "reg",
            2, base, 2, 0xc0, 2, CM5_MIP_MSI, 2, 0x1000);
        qemu_fdt_setprop(fdt, node, "msi-controller", NULL, 0);
        qemu_fdt_setprop_cells(fdt, node, "msi-ranges", s->gic_phandle,
                              0, spi_base, 1, count);
        qemu_fdt_setprop_cell(fdt, node, "brcm,msi-offset", first);
        qemu_fdt_setprop_cell(fdt, node, "phandle", s->mip_phandle[n]);
    }
}

static AddressSpace *cm5_dma_space(PCIBus *bus, void *opaque, int devfn)
{
    return opaque;
}

static const PCIIOMMUOps cm5_dma_ops = {
    .get_address_space = cm5_dma_space,
};

static void cm5_msi(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    DeviceState *dev;
    const char *node = "/interrupt-controller@107fff9000/v2m@1202000000";
    unsigned i;

    if (s->native_mip) {
        cm5_native_mip(s);
        return;
    }
    dev = qdev_new("arm-gicv2m");
    /* Generic MIP substitute, deliberately at a different address. */
    qdev_prop_set_uint32(dev, "base-spi", CM5_MSI_FIRST);
    qdev_prop_set_uint32(dev, "num-spi", CM5_MSI_COUNT);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, CM5_MSI_FRAME);
    for (i = 0; i < CM5_MSI_COUNT; i++) {
        sysbus_connect_irq(SYS_BUS_DEVICE(dev), i,
                           qdev_get_gpio_in(s->gic, CM5_MSI_FIRST + i));
    }
    qemu_fdt_add_subnode(fdt, node);
    qemu_fdt_setprop_string(fdt, node, "compatible", "arm,gic-v2m-frame");
    cm5_reg(fdt, node, CM5_MSI_FRAME, 0x1000);
    qemu_fdt_setprop(fdt, node, "msi-controller", NULL, 0);
    qemu_fdt_setprop_cell(fdt, node, "phandle", s->msi_phandle);
}

static PCIBus *cm5_pcie(CM5IODevState *s, unsigned index)
{
    MachineState *ms = MACHINE(s);
    void *fdt = ms->fdt;
    hwaddr ecam = index ? CM5_EXP_ECAM : CM5_RP1_ECAM;
    hwaddr window = index ? CM5_EXP_WINDOW : CM5_RP1_WINDOW;
    hwaddr pio = index ? CM5_EXP_PIO : CM5_RP1_PIO;
    const char *name = index ? "expansion-host" : "rp1-host";
    g_autofree char *node = g_strdup_printf("/pcie@%" HWADDR_PRIx, ecam);
    DeviceState *dev = qdev_new(TYPE_GPEX_HOST);
    SysBusDevice *sb = SYS_BUS_DEVICE(dev);
    PCIBus *bus;
    unsigned i, pin;
    uint32_t map[4 * 4 * 10];
    unsigned count = 0;

    object_property_add_child(OBJECT(s), name, OBJECT(dev));
    dev->id = g_strdup(name);
    qdev_prop_set_string(dev, "x-bus-name",
                         index ? "cm5-expansion" : "cm5-rp1");
    qdev_prop_set_string(dev, "x-root-bus-path", index ? "0001:00" : "0002:00");
    sysbus_realize_and_unref(sb, &error_fatal);
    memory_region_init_alias(&s->ecam[index], OBJECT(s), name,
                             sysbus_mmio_get_region(sb, 0), 0, CM5_ECAM_SIZE);
    memory_region_add_subregion(get_system_memory(), ecam, &s->ecam[index]);
    memory_region_init_alias(&s->pci_mmio[index], OBJECT(s), name,
                             sysbus_mmio_get_region(sb, 1),
                             CM5_PCI_BUS_BASE, CM5_PCI_SIZE);
    memory_region_add_subregion(get_system_memory(), window,
                                &s->pci_mmio[index]);
    sysbus_mmio_map(sb, 2, pio);
    for (i = 0; i < 4; i++) {
        unsigned irq = (index ? 108 : 100) + i;
        sysbus_connect_irq(sb, i, qdev_get_gpio_in(s->gic, irq));
        gpex_set_irq_num(GPEX_HOST(dev), i, irq);
    }
    bus = PCI_HOST_BRIDGE(dev)->bus;
    if (s->native_mip) {
        /*
         * Published per-host inbound MSI aperture. The two PCI hosts share
         * the bus address but route to different MIPs, so a CPU-global alias
         * would be incorrect. Ordinary DMA remains the Phase 6 substitute.
         */
        memory_region_init(&s->dma_root[index], OBJECT(s), name, UINT64_MAX);
        memory_region_init_alias(&s->dma_identity[index], OBJECT(s), name,
                                  get_system_memory(), 0, UINT64_MAX);
        memory_region_add_subregion(&s->dma_root[index], 0,
                                     &s->dma_identity[index]);
        memory_region_init_alias(&s->dma_msi[index], OBJECT(s), name,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(s->mip[index]), 1), 0, 0x1000);
        memory_region_add_subregion_overlap(&s->dma_root[index], CM5_MIP_MSI,
                                             &s->dma_msi[index], 1);
        address_space_init(&s->dma_as[index], &s->dma_root[index], name);
        pci_setup_iommu(bus, &cm5_dma_ops, &s->dma_as[index]);
    }
    qemu_fdt_add_subnode(fdt, node);
    qemu_fdt_setprop_string(fdt, node, "compatible", "pci-host-ecam-generic");
    qemu_fdt_setprop_string(fdt, node, "device_type", "pci");
    qemu_fdt_setprop_cell(fdt, node, "#address-cells", 3);
    qemu_fdt_setprop_cell(fdt, node, "#size-cells", 2);
    qemu_fdt_setprop_cell(fdt, node, "#interrupt-cells", 1);
    qemu_fdt_setprop_cell(fdt, node, "linux,pci-domain", index ? 1 : 2);
    qemu_fdt_setprop_cells(fdt, node, "bus-range", 0, 15);
    cm5_reg(fdt, node, ecam, CM5_ECAM_SIZE);
    qemu_fdt_setprop_cells(fdt, node, "ranges",
        0x02000000, 0, CM5_PCI_BUS_BASE, window >> 32, (uint32_t)window,
        0, CM5_PCI_SIZE,
        0x01000000, 0, 0, pio >> 32, (uint32_t)pio, 0, 0x10000);
    qemu_fdt_setprop_cells(fdt, node, "msi-parent",
        s->native_mip ? s->mip_phandle[index] : s->msi_phandle);
    qemu_fdt_setprop(fdt, node, "dma-coherent", NULL, 0);
    /* Generic identity DMA, not BCM2712's inbound translation/MIP aperture. */
    qemu_fdt_setprop_cells(fdt, node, "dma-ranges", 0x03000000, 0, 0,
                            0, 0, ms->ram_size >> 32, (uint32_t)ms->ram_size);
    if (s->native_mip) {
        hwaddr target = index ? CM5_MIP1 : CM5_MIP0;
        qemu_fdt_setprop_cells(fdt, node, "dma-ranges",
            0x03000000, 0, 0, 0, 0,
            ms->ram_size >> 32, (uint32_t)ms->ram_size,
            0x03000000, 0xff, 0xfffff000,
            target >> 32, (uint32_t)target, 0, 0x1000);
    }
    qemu_fdt_setprop_cells(fdt, node, "interrupt-map-mask", 0x1800, 0, 0, 7);
    for (i = 0; i < 4; i++) {
        for (pin = 1; pin <= 4; pin++) {
            uint32_t entry[] = { i << 11, 0, 0, pin, s->gic_phandle,
                0, 0, 0, (index ? 108 : 100) + (i + pin - 1) % 4, 4 };
            unsigned j;
            for (j = 0; j < ARRAY_SIZE(entry); j++) {
                map[count++] = cpu_to_be32(entry[j]);
            }
        }
    }
    qemu_fdt_setprop(fdt, node, "interrupt-map", map, count * sizeof(*map));
    qemu_fdt_setprop_string(fdt, node, "qemu,substitute-for",
                            index ? "BCM2712 PCIe1, CM5IO M.2 x1" :
                                    "BCM2712 PCIe2, internal RP1 x4");
    return bus;
}

static void cm5_rp1_dt(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    uint32_t irq = qemu_fdt_alloc_phandle(fdt);
    uint32_t clock = qemu_fdt_alloc_phandle(fdt);
    const char *parent = "/rp1-peripherals";
    const char *rp1 = "/rp1-peripherals/rp1";
    const char *spi = "/rp1-peripherals/rp1/spi@50000";

    cm5_clock(s, "/rp1-fixed-clock", 200000000, clock);
    qemu_fdt_add_subnode(fdt, parent);
    qemu_fdt_setprop_string(fdt, parent, "compatible", "simple-bus");
    qemu_fdt_setprop_cell(fdt, parent, "#address-cells", 2);
    qemu_fdt_setprop_cell(fdt, parent, "#size-cells", 2);
    qemu_fdt_setprop(fdt, parent, "ranges", NULL, 0);
    qemu_fdt_add_subnode(fdt, rp1);
    qemu_fdt_setprop_string(fdt, rp1, "compatible", "simple-bus");
    qemu_fdt_setprop_cell(fdt, rp1, "#address-cells", 2);
    qemu_fdt_setprop_cell(fdt, rp1, "#size-cells", 2);
    qemu_fdt_setprop_cell(fdt, rp1, "#interrupt-cells", 2);
    qemu_fdt_setprop(fdt, rp1, "interrupt-controller", NULL, 0);
    qemu_fdt_setprop_cell(fdt, rp1, "phandle", irq);
    qemu_fdt_setprop_sized_cells(fdt, rp1, "ranges", 2, 0,
                                2, CM5_RP1_WINDOW, 2, 4 * MiB);
    if (!s->header_spi) {
        return;
    }
    qemu_fdt_add_subnode(fdt, spi);
    qemu_fdt_setprop_string(fdt, spi, "compatible",
                                       "snps,dw-apb-ssi");
    cm5_reg(fdt, spi, 0x50000, 0x1000);
    qemu_fdt_setprop_cells(fdt, spi, "interrupts", 19, 4);
    qemu_fdt_setprop_cell(fdt, spi, "interrupt-parent", irq);
    qemu_fdt_setprop_cell(fdt, spi, "clocks", clock);
    qemu_fdt_setprop_cell(fdt, spi, "reg-io-width", 4);
    /* Only CE0/CE1 are routed through the 40-pin header. */
    qemu_fdt_setprop_cell(fdt, spi, "num-cs", 2);
    qemu_fdt_setprop_cell(fdt, spi, "#address-cells", 1);
    qemu_fdt_setprop_cell(fdt, spi, "#size-cells", 0);
    qemu_fdt_setprop_string(fdt, "/aliases", "spi0", spi);
    /* Explicit protocol driver attachment via guest driver_override. */
    qemu_fdt_add_subnode(fdt, "/rp1-peripherals/rp1/spi@50000/test-slave@0");
    qemu_fdt_setprop_string(fdt,
        "/rp1-peripherals/rp1/spi@50000/test-slave@0", "compatible",
        "qemu,ssi-test-slave");
    qemu_fdt_setprop_cell(fdt,
        "/rp1-peripherals/rp1/spi@50000/test-slave@0", "reg", 0);
    qemu_fdt_setprop_cell(fdt,
        "/rp1-peripherals/rp1/spi@50000/test-slave@0", "spi-max-frequency",
        10000000);
}

/* Native BCM2712 logical link and PCI transaction path. */
static void cm5_native_pcie(CM5IODevState *s, unsigned index)
{
    void *fdt = MACHINE(s)->fdt;
    hwaddr base = index ? 0x1000110000ULL : 0x1000120000ULL;
    unsigned intx = index ? 219 : 229;
    DeviceState *dev = qdev_new(TYPE_BCM2712_PCIE);
    g_autofree char *node = g_strdup_printf("/pcie@%" HWADDR_PRIx, base);
    uint32_t clock = qemu_fdt_alloc_phandle(fdt);
    g_autofree char *clk = g_strdup_printf("/pcie%u-fixed-clock", index);
    uint32_t map[4 * 10];
    unsigned pin, j, n = 0;
    const char names[] = "pcie\0msi";

    object_property_add_child(OBJECT(s), index ? "native-expansion" :
                              "native-rp1", OBJECT(dev));
    qdev_prop_set_uint32(dev, "controller", index ? 1 : 2);
    qdev_prop_set_bit(dev, "connect-rp1", !index);
    qdev_prop_set_bit(dev, "rp1-gpio-lab", !index && s->rp1_gpio_lab);
    qdev_prop_set_uint64(dev, "ram-size", MACHINE(s)->ram_size);
    object_property_set_link(OBJECT(dev), "msi-target",
        OBJECT(sysbus_mmio_get_region(SYS_BUS_DEVICE(s->mip[index]), 1)),
        &error_fatal);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, base);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 1,
                   index ? 0x1b80000000ULL : 0x1f00000000ULL);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 2,
                   index ? 0x1800000000ULL : 0x1c00000000ULL);
    for (pin = 0; pin < 4; pin++) {
        sysbus_connect_irq(SYS_BUS_DEVICE(dev), pin,
                           qdev_get_gpio_in(s->gic, intx + pin));
    }
    qemu_fdt_add_subnode(fdt, node);
    if (!index) {
        const char *rp1 = "/pcie@1000120000/rp1";

        /*
         * The real MFD locates this simple-bus node by name. Only modeled
         * children will be added; this is not an import of the captured DT.
         */
        qemu_fdt_add_subnode(fdt, rp1);
        qemu_fdt_setprop_string(fdt, rp1, "compatible", "simple-bus");
        qemu_fdt_setprop_cell(fdt, rp1, "#address-cells", 2);
        qemu_fdt_setprop_cell(fdt, rp1, "#size-cells", 2);
        qemu_fdt_setprop_cell(fdt, rp1, "#interrupt-cells", 2);
        qemu_fdt_setprop(fdt, rp1, "interrupt-controller", NULL, 0);
        qemu_fdt_setprop_cell(fdt, rp1, "phandle", qemu_fdt_alloc_phandle(fdt));
        qemu_fdt_setprop_cells(fdt, rp1, "ranges",
            0xc0, 0x40000000, 0x02000000, 0, 0, 0, 0x400000);
        {
            const char *clks = "/pcie@1000120000/rp1/clocks@18000";
            const char *spi = "/pcie@1000120000/rp1/spi@50000";
            const char *slave = "/pcie@1000120000/rp1/spi@50000/test-slave@0";
            uint32_t xosc = qemu_fdt_alloc_phandle(fdt);
            uint32_t clocks = qemu_fdt_alloc_phandle(fdt);
            uint32_t irq = qemu_fdt_get_phandle(fdt, rp1);

            cm5_clock(s, "/rp1-xosc", 50000000, xosc);
            qemu_fdt_add_subnode(fdt, clks);
            qemu_fdt_setprop_string(fdt, clks, "compatible",
                                   "raspberrypi,rp1-clocks");
            qemu_fdt_setprop_cell(fdt, clks, "#clock-cells", 1);
            qemu_fdt_setprop_cell(fdt, clks, "phandle", clocks);
            qemu_fdt_setprop_cell(fdt, clks, "clocks", xosc);
            qemu_fdt_setprop_cells(fdt, clks, "reg",
                                   0xc0, 0x40018000, 0, 0x10038);
            if (s->header_spi) {
                qemu_fdt_add_subnode(fdt, spi);
                qemu_fdt_setprop_string(fdt, spi, "compatible",
                                       "snps,dw-apb-ssi");
                qemu_fdt_setprop_cells(fdt, spi, "reg",
                                       0xc0, 0x40050000, 0, 0x130);
                qemu_fdt_setprop_cells(fdt, spi, "clocks", clocks, 12);
                qemu_fdt_setprop_cells(fdt, spi, "interrupts", 19, 4);
                qemu_fdt_setprop_cell(fdt, spi, "interrupt-parent", irq);
                qemu_fdt_setprop_cell(fdt, spi, "reg-io-width", 4);
                qemu_fdt_setprop_cell(fdt, spi, "num-cs", 2);
                qemu_fdt_setprop_cell(fdt, spi, "#address-cells", 1);
                qemu_fdt_setprop_cell(fdt, spi, "#size-cells", 0);
                qemu_fdt_setprop_string(fdt, "/aliases", "spi0", spi);
                qemu_fdt_add_subnode(fdt, slave);
                qemu_fdt_setprop_string(fdt, slave, "compatible",
                                       "qemu,ssi-test-slave");
                qemu_fdt_setprop_cell(fdt, slave, "reg", 0);
                qemu_fdt_setprop_cell(fdt, slave, "spi-max-frequency",
                                     10000000);
            }
        }
    }
    cm5_clock(s, clk, 54000000, clock);
    qemu_fdt_setprop_string(fdt, node, "compatible", "brcm,bcm2712-pcie");
    qemu_fdt_setprop_string(fdt, node, "device_type", "pci");
    qemu_fdt_setprop_string(fdt, node, "qemu,implementation",
                          "logical link, indexed config and programmed address windows");
    cm5_reg(fdt, node, base, 0x9310);
    qemu_fdt_setprop_cell(fdt, node, "#address-cells", 3);
    qemu_fdt_setprop_cell(fdt, node, "#size-cells", 2);
    qemu_fdt_setprop_cell(fdt, node, "#interrupt-cells", 1);
    qemu_fdt_setprop_cell(fdt, node, "linux,pci-domain", index ? 1 : 2);
    qemu_fdt_setprop_cells(fdt, node, "bus-range", 0, 15);
    qemu_fdt_setprop_cell(fdt, node, "num-lanes", index ? 1 : 4);
    qemu_fdt_setprop_cell(fdt, node, "max-link-speed", 2);
    qemu_fdt_setprop_cells(fdt, node, "clocks", clock);
    qemu_fdt_setprop_string(fdt, node, "clock-names", "sw_pcie");
    qemu_fdt_setprop_cells(fdt, node, "interrupts", 0, intx + 4, 4,
                           0, intx + 5, 4);
    qemu_fdt_setprop(fdt, node, "interrupt-names", names, sizeof(names));
    qemu_fdt_setprop_cells(fdt, node, "msi-parent", s->mip_phandle[index]);
    qemu_fdt_setprop_cells(fdt, node, "interrupt-map-mask", 0, 0, 0, 7);
    for (pin = 1; pin <= 4; pin++) {
        uint32_t entry[] = { 0, 0, 0, pin, s->gic_phandle,
                            0, 0, 0, intx + pin - 1, 4 };
        for (j = 0; j < ARRAY_SIZE(entry); j++) {
            map[n++] = cpu_to_be32(entry[j]);
        }
    }
    qemu_fdt_setprop(fdt, node, "interrupt-map", map, sizeof(map));
    qemu_fdt_setprop_cells(fdt, node, "ranges",
        0x02000000, 0, index ? 0x80000000 : 0,
        index ? 0x1b : 0x1f, index ? 0x80000000 : 0,
        0, index ? 0x80000000 : 0xfffffffc,
        0x43000000, 4, 0, index ? 0x18 : 0x1c, 0,
        3, index ? 0x80000000 : 0);
    qemu_fdt_setprop_cells(fdt, node, "dma-ranges",
        0x03000000, 0x10, 0, 0, 0, 0x10, 0,
        0x03000000, 0xff, 0xfffff000, 0x10,
        index ? 0x131000 : 0x130000, 0, 0x1000);
}

static void cm5_connectors(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    const char *root = "/cm5io-connectors";
    static const struct {
        const char *name;
        const char *routing;
        const char *implementation;
    } profile[] = {
        { "header-spi0", "GPIO10 MOSI pin19; GPIO9 MISO pin21; GPIO11 SCLK "
          "pin23; GPIO8 CE0 pin24; GPIO7 CE1 pin26", "RP1 SPI0, fixed route" },
        { "header-uart0", "GPIO14 TX pin8; GPIO15 RX pin10",
          "generic PL011 substitute, serial1, not RP1 UART registers" },
        { "header-i2c1", "GPIO2 SDA pin3; GPIO3 SCL pin5",
          "not implemented; no I2C controller attached" },
        { "header-gpio", "40-pin HAT header, GPIO0..27",
          "not implemented; no RP1 GPIO/pinmux registers" },
        { "ethernet", "CM5 Ethernet PHY to CM5IO RJ45 magjack",
          "RP1 MAC/PHY not implemented; optional virtio-net on expansion bus" },
        { "usb", "RP1 USB3 to two Type-A; BCM2712 USB2 to Type-C",
          "not implemented; optional generic qemu-xhci on expansion bus" },
        { "pcie-expansion", "BCM2712 PCIe1 x1 to CM5IO M.2 M-key",
          "independent GPEX substitute, cm5-expansion bus" },
        { "rtc", "CM5 PMIC RTC, CM5IO battery connector",
          "optional PL031 substitute; no PMIC registers or battery model" },
    };
    unsigned i;

    /* Metadata only: these strings do not create Linux hardware interfaces. */
    qemu_fdt_add_subnode(fdt, root);
    qemu_fdt_setprop_cell(fdt, root, "qemu,gpio-vref-millivolt", s->gpio_vref);
    qemu_fdt_setprop_string(fdt, root, "qemu,pinmux",
                            "fixed SPI0 route; GPIO pinmux not implemented");
    for (i = 0; i < ARRAY_SIZE(profile); i++) {
        g_autofree char *node = g_strdup_printf("%s/%s", root, profile[i].name);
        bool enabled = i == 0 ? s->header_spi :
                       i == 1 ? s->header_uart :
                       i == 6 ? s->expansion && !s->native_pcie :
                       i == 7 ? s->test_rtc : false;

        qemu_fdt_add_subnode(fdt, node);
        qemu_fdt_setprop_string(fdt, node, "qemu,routing", profile[i].routing);
        qemu_fdt_setprop_string(fdt, node, "qemu,implementation",
            s->native_pcie && i == 6 ?
            "native root port; no expansion endpoint attached" :
            profile[i].implementation);
        qemu_fdt_setprop_string(fdt, node, "status",
                                enabled ? "okay" : "disabled");
    }
}

static void cm5_emmc(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    const char *node = "/mmc@1000fff000";
    const char compat[] = "brcm,bcm2712-sdhci\0brcm,sdhci-brcmstb";
    const char names[] = "host\0cfg";
    const char pins[] = "default\0sd-express";
    uint32_t clock = qemu_fdt_alloc_phandle(fdt);
    DeviceState *dev = qdev_new(TYPE_BCM2712_SDHCI);

    object_property_add_child(OBJECT(s), "emmc-host", OBJECT(dev));
    qdev_prop_set_bit(dev, "dma", s->emmc_dma);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, CM5_EMMC_HOST);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 1, CM5_EMMC_CFG);
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0,
                       qdev_get_gpio_in(s->gic, CM5_EMMC_IRQ));
    cm5_clock(s, "/emmc-fixed-clock", 200000000, clock);
    qemu_fdt_add_subnode(fdt, node);
    qemu_fdt_setprop(fdt, node, "compatible", compat, sizeof(compat));
    qemu_fdt_setprop_sized_cells(fdt, node, "reg",
        2, CM5_EMMC_HOST, 2, 0x260, 2, CM5_EMMC_CFG, 2, 0x200);
    qemu_fdt_setprop(fdt, node, "reg-names", names, sizeof(names));
    qemu_fdt_setprop_cells(fdt, node, "interrupts", 0, CM5_EMMC_IRQ, 4);
    qemu_fdt_setprop_cell(fdt, node, "clocks", clock);
    qemu_fdt_setprop_string(fdt, node, "clock-names", "sw_sdio");
    qemu_fdt_setprop_cell(fdt, node, "bus-width", 8);
    qemu_fdt_setprop_cell(fdt, node, "max-frequency", 25000000);
    qemu_fdt_setprop(fdt, node, "non-removable", NULL, 0);
    qemu_fdt_setprop(fdt, node, "no-sd", NULL, 0);
    qemu_fdt_setprop(fdt, node, "no-sdio", NULL, 0);
    /*
     * Explicit empty pin states: no pad/pinmux emulation. The public driver
     * looks up both states even without SD Express resources. Linux supports
     * empty pinctrl states for hardware which needs no pin programming here.
     */
    qemu_fdt_setprop(fdt, node, "pinctrl-names", pins, sizeof(pins));
    qemu_fdt_setprop(fdt, node, "pinctrl-0", NULL, 0);
    qemu_fdt_setprop(fdt, node, "pinctrl-1", NULL, 0);
    qemu_fdt_setprop_string(fdt, "/aliases", "mmc0", node);
}

/* Opt-in generator transformation: only the implemented GPIO20/21 slice. */
static void cm5_gpio_lab_dt(CM5IODevState *s)
{
    void *fdt = MACHINE(s)->fdt;
    const char *rp1 = "/pcie@1000120000/rp1";
    const char *gpio = "/pcie@1000120000/rp1/gpio@d0000";
    uint32_t phandle = qemu_fdt_alloc_phandle(fdt);
    const char names[] = "\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0"
                         "GPIO20\0GPIO21\0";

    qemu_fdt_add_subnode(fdt, gpio);
    qemu_fdt_setprop_string(fdt, gpio, "compatible", "raspberrypi,rp1-gpio");
    qemu_fdt_setprop_cells(fdt, gpio, "reg",
        0xc0, 0x400d0000, 0, 0xc000,
        0xc0, 0x400e0000, 0, 0xc000,
        0xc0, 0x400f0000, 0, 0xc000);
    qemu_fdt_setprop_cell(fdt, gpio, "phandle", phandle);
    qemu_fdt_setprop_cell(fdt, gpio, "interrupt-parent",
                          qemu_fdt_get_phandle(fdt, rp1));
    qemu_fdt_setprop_cells(fdt, gpio, "interrupts", 0, 4);
    qemu_fdt_setprop(fdt, gpio, "gpio-controller", NULL, 0);
    qemu_fdt_setprop_cell(fdt, gpio, "#gpio-cells", 2);
    qemu_fdt_setprop(fdt, gpio, "interrupt-controller", NULL, 0);
    qemu_fdt_setprop_cell(fdt, gpio, "#interrupt-cells", 2);
    qemu_fdt_setprop_cells(fdt, gpio, "gpio-ranges", phandle, 0, 0, 54);
    qemu_fdt_setprop_cells(fdt, gpio, "gpio-reserved-ranges", 0, 20, 22, 32);
    qemu_fdt_setprop(fdt, gpio, "gpio-line-names", names, sizeof(names) - 1);
    qemu_fdt_setprop_string(fdt, "/cm5io-connectors/header-gpio",
                            "status", "okay");
    qemu_fdt_setprop_string(fdt, "/cm5io-connectors/header-gpio",
        "qemu,implementation", "bounded RP1 GPIO20/21; "
        "synthetic GPIO20->21 loopback");
    qemu_fdt_setprop_string(fdt, "/cm5io-connectors", "qemu,pinmux",
        "GPIO20/21 SYS_RIO only; SPI0 logical route remains independent");
}

static void *cm5_get_dtb(const struct arm_boot_info *info, int *size)
{
    CM5IODevState *s = container_of(info, CM5IODevState, bootinfo);
    *size = s->fdt_size;
    return g_memdup2(MACHINE(s)->fdt, *size);
}

static void cm5_init(MachineState *ms)
{
    CM5IODevState *s = CM5IO_DEV(ms);
    DeviceState *rp1;
    PCIBus *bus;
    void *fdt;

    if (!tcg_enabled() && !qtest_enabled()) {
        error_report("cm5io-dev currently supports TCG only");
        exit(1);
    }
    if (ms->ram_size > 8 * GiB || ms->ram_size < 512 * MiB) {
        error_report("cm5io-dev currently supports 512 MiB..8 GiB RAM");
        exit(1);
    }
    if (ms->firmware || ms->dtb) {
        error_report("cm5io-dev requires generated DT and direct -kernel boot");
        exit(1);
    }
    if (s->rp1_gpio_lab && !s->native_pcie) {
        error_report("rp1-gpio-lab requires native-pcie=on");
        exit(1);
    }
    if (s->native_pcie && !s->native_mip) {
        error_report("native-pcie requires native-mip=on");
        exit(1);
    }
    memory_region_add_subregion(get_system_memory(), 0, ms->ram);
    ms->fdt = fdt = create_device_tree(&s->fdt_size);
    qemu_fdt_setprop_string(fdt, "/", "model",
        "Experimental CM5 + CM5IO development platform (partial BCM2712)");
    qemu_fdt_setprop_string(fdt, "/", "compatible", "qemu,cm5io-dev");
    qemu_fdt_setprop_cell(fdt, "/", "#address-cells", 2);
    qemu_fdt_setprop_cell(fdt, "/", "#size-cells", 2);
    qemu_fdt_add_subnode(fdt, "/chosen");
    qemu_fdt_add_subnode(fdt, "/aliases");
    qemu_fdt_add_subnode(fdt, "/memory@0");
    qemu_fdt_setprop_string(fdt, "/memory@0", "device_type", "memory");
    cm5_reg(fdt, "/memory@0", 0, ms->ram_size);
    s->gic_phandle = qemu_fdt_alloc_phandle(fdt);
    s->msi_phandle = qemu_fdt_alloc_phandle(fdt);
    s->clk_phandle = qemu_fdt_alloc_phandle(fdt);
    cm5_clock(s, "/uart-fixed-clock", 48000000, s->clk_phandle);
    cm5_cpus_gic(s);
    cm5_msi(s);
    if (s->native_emmc) {
        cm5_emmc(s);
    }
    cm5_uart(s, "/serial@107d001000", CM5_UART10, 121,
              serial_hd(0), true);
    if (s->header_uart) {
        cm5_uart(s, "/serial@1203000000", CM5_HEADER_UART, 105,
                  serial_hd(1), false);
    }
    if (s->test_rtc) {
        const char *node = "/rtc@1203010000";
        const char compat[] = "arm,pl031\0arm,primecell";
        sysbus_create_simple("pl031", CM5_TEST_RTC,
                              qdev_get_gpio_in(s->gic, 104));
        qemu_fdt_add_subnode(fdt, node);
        qemu_fdt_setprop(fdt, node, "compatible", compat, sizeof(compat));
        cm5_reg(fdt, node, CM5_TEST_RTC, 0x1000);
        qemu_fdt_setprop_cells(fdt, node, "interrupts", 0, 104, 4);
        qemu_fdt_setprop_cell(fdt, node, "clocks", s->clk_phandle);
        qemu_fdt_setprop_string(fdt, node, "clock-names", "apb_pclk");
    }
    if (s->native_pcie) {
        cm5_native_pcie(s, 0);
        if (s->expansion) {
            cm5_native_pcie(s, 1);
        }
    } else {
        bus = cm5_pcie(s, 0);
        rp1 = DEVICE(pci_new(PCI_DEVFN(1, 0), "rp1-pci"));
        object_property_add_child(OBJECT(s), "rp1", OBJECT(rp1));
        pci_realize_and_unref(PCI_DEVICE(rp1), bus, &error_fatal);
        if (s->expansion) {
            cm5_pcie(s, 1);
        }
        cm5_rp1_dt(s);
    }
    cm5_connectors(s);
    if (s->rp1_gpio_lab) {
        cm5_gpio_lab_dt(s);
    }
    s->bootinfo.ram_size = ms->ram_size;
    s->bootinfo.loader_start = 0;
    s->bootinfo.board_id = -1;
    s->bootinfo.psci_conduit = QEMU_PSCI_CONDUIT_SMC;
    s->bootinfo.get_dtb = cm5_get_dtb;
    arm_load_kernel(ARM_CPU(first_cpu), ms, &s->bootinfo);
}

static void cm5_instance_init(Object *obj)
{
    CM5IODevState *s = CM5IO_DEV(obj);
    s->header_spi = s->header_uart = s->expansion = s->test_rtc = true;
    s->gpio_vref = 3300;
}

static char *cm5_get_vref(Object *obj, Error **errp)
{
    return g_strdup_printf("%u", CM5IO_DEV(obj)->gpio_vref);
}

static void cm5_set_vref(Object *obj, const char *value, Error **errp)
{
    if (strcmp(value, "1800") && strcmp(value, "3300")) {
        error_setg(errp, "gpio-vref must be 1800 or 3300 (metadata only)");
        return;
    }
    CM5IO_DEV(obj)->gpio_vref = !strcmp(value, "1800") ? 1800 : 3300;
}

static void cm5_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    static const char * const cpus[] = {
        ARM_CPU_TYPE_NAME("cortex-a76"), NULL
    };

    mc->pci_allow_0_address = true;
    mc->desc = "Experimental CM5 + CM5IO (partial BCM2712, generic PCI/MSI)";
    mc->init = cm5_init;
    mc->default_cpu_type = ARM_CPU_TYPE_NAME("cortex-a76");
    mc->valid_cpu_types = cpus;
    mc->default_cpus = mc->max_cpus = 4;
    mc->default_ram_size = 2 * GiB;
    mc->default_ram_id = "cm5io.ram";
    mc->minimum_page_bits = 12;
    mc->no_floppy = mc->no_cdrom = mc->no_parallel = true;
    object_class_property_add_bool_ptr(oc, "header-spi",
        offsetof(CM5IODevState, header_spi), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "header-uart",
        offsetof(CM5IODevState, header_uart), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "pcie-expansion",
        offsetof(CM5IODevState, expansion), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "test-rtc",
        offsetof(CM5IODevState, test_rtc), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "native-mip",
        offsetof(CM5IODevState, native_mip), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "native-emmc",
        offsetof(CM5IODevState, native_emmc), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "emmc-dma",
        offsetof(CM5IODevState, emmc_dma), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "rp1-gpio-lab",
        offsetof(CM5IODevState, rp1_gpio_lab), OBJ_PROP_FLAG_READWRITE);
    object_class_property_add_bool_ptr(oc, "native-pcie",
        offsetof(CM5IODevState, native_pcie), OBJ_PROP_FLAG_READWRITE);
    object_class_property_set_description(oc, "native-pcie",
        "BCM2712 logical PCIe/RP1 link and programmed address windows");
    object_class_property_add_str(oc, "gpio-vref", cm5_get_vref, cm5_set_vref);
    object_class_property_set_description(oc, "gpio-vref",
        "CM5IO R4/R5 selection: 1800 or 3300 mV metadata; no electrical model");
}

static const TypeInfo cm5_type = {
    .name = TYPE_CM5IO_DEV,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(CM5IODevState),
    .instance_init = cm5_instance_init,
    .class_init = cm5_class_init,
    .is_available = target_aarch64,
};

static void cm5_register_types(void)
{
    type_register_static(&cm5_type);
}
type_init(cm5_register_types)

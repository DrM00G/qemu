/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local CM5IO machine tests, not intended for upstream. */
#include "qemu/osdep.h"
#include "hw/arm/cm5io-dev.h"
#include "libqtest.h"

static void test_machine(void)
{
    QTestState *q = qtest_init("-M cm5io-dev -m 512M -nodefaults "
                              "-device ssi-test-slave,bus=spi,cs=0");
    uint64_t cfg = CM5_RP1_ECAM + 0x8000;
    uint64_t spi = CM5_RP1_WINDOW + 0x50000;
    unsigned i;

    /* RAM at physical zero, plus high-address GIC/UART and two PCI domains. */
    qtest_writel(q, 0x1000, 0x5a1234a5);
    g_assert_cmphex(qtest_readl(q, 0x1000), ==, 0x5a1234a5);
    g_assert_cmphex(qtest_readl(q, cfg), ==, 0x00011de4);
    g_assert_cmphex(qtest_readl(q, CM5_EXP_ECAM), ==, 0x00081b36);
    g_assert_cmphex(qtest_readl(q, CM5_UART10 + 0xfe0), ==, 0x11);
    g_assert_cmphex(qtest_readl(q, CM5_GIC_DIST + 4) & 31, ==, 15);
    g_assert_cmphex(qtest_readl(q, CM5_MSI_FRAME + 8), ==, (160 << 16) | 128);
    qtest_writel(q, cfg + 0x10, CM5_PCI_BUS_BASE + 0x400000);
    qtest_writel(q, cfg + 0x14, CM5_PCI_BUS_BASE);
    qtest_writew(q, cfg + 4, 6);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_WINDOW), ==, 0x20001927);
    qtest_writel(q, spi, 7 << 16);
    qtest_writel(q, spi + 0x14, 200);
    qtest_writel(q, spi + 0x10, 1);
    qtest_writel(q, spi + 8, 1);
    for (i = 1; i <= 4; i++) {
        qtest_writel(q, spi + 0x60, i * 0x10);
    }
    for (i = 1; i <= 4; i++) {
        qtest_clock_step(q, 8000);
    }
    for (i = 1; i <= 4; i++) {
        g_assert_cmphex(qtest_readl(q, spi + 0x60), ==, (i * 0x10) ^ 0xa5);
    }
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    qtest_writel(q, cfg + 0x14, CM5_PCI_BUS_BASE);
    qtest_writew(q, cfg + 4, 6);
    g_assert_cmphex(qtest_readl(q, spi + 8), ==, 0);
    qtest_quit(q);
}

static void test_options(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,header-spi=off,header-uart=off,"
                              "pcie-expansion=off,test-rtc=off,gpio-vref=1800 "
                              "-m 512M -nodefaults");
    g_assert_cmphex(qtest_readl(q, CM5_RP1_ECAM + 0x8000), ==, 0x00011de4);
    g_assert_cmphex(qtest_readl(q, CM5_EXP_ECAM), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_HEADER_UART + 0xfe0), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_TEST_RTC + 0xfe0), ==, 0);
    qtest_quit(q);
}

static void test_native_probe(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on "
                              "-m 512M -nodefaults");
    const uint64_t hosts[] = { 0x1000110000ULL, 0x1000120000ULL };
    unsigned i;

    for (i = 0; i < ARRAY_SIZE(hosts); i++) {
        uint64_t h = hosts[i];

        g_assert_cmphex(qtest_readl(q, h), ==, 0x271214e4);
        g_assert_cmphex(qtest_readb(q, h + 0x0e) & 0x7f, ==, 1);
        qtest_writeb(q, h + 0x19, 1);
        g_assert_cmphex(qtest_readb(q, h + 0x19), ==, 1);
        g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
        g_assert_cmphex(qtest_readl(q, h + 0x9210), ==, 2);
        qtest_writel(q, h + 0x9210, 0);
        g_assert_cmphex(qtest_readl(q, h + 0x9210), ==, 0);
        qtest_writel(q, h + 0x402c, 0x1234500f);
        g_assert_cmphex(qtest_readl(q, h + 0x402c), ==, 0x1234500f);
        /* Native driver selects port0/0x1f then starts an MDIO write. */
        qtest_writel(q, h + 0x1100, 0x1f);
        qtest_writel(q, h + 0x1104, 0x80001600);
        qtest_clock_step(q, 1000000);
        g_assert_cmphex(qtest_readl(q, h + 0x1104), ==, 0x1600);
        g_assert_cmphex(qtest_readl(q, h + 0x1108), ==, 0);
        /* Neither status writes nor PERST release manufacture a link. */
        qtest_writel(q, h + 0x4064, 4);
        qtest_writel(q, h + 0x4068, 0xb0);
        g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
        qtest_writel(q, h + 0x9000, 1 << 20);
        g_assert_cmphex(qtest_readl(q, h + 0x8000), ==, 0xffffffff);
    }
    /* Controller instances are isolated; the disabled third host is absent. */
    qtest_writel(q, hosts[0] + 0x402c, 0x5555);
    g_assert_cmphex(qtest_readl(q, hosts[1] + 0x402c), ==, 0x1234500f);
    g_assert_cmphex(qtest_readl(q, 0x1000104068ULL), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_ECAM), ==, 0);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    g_assert_cmphex(qtest_readl(q, hosts[0] + 0x402c), ==, 0);
    g_assert_cmphex(qtest_readl(q, hosts[1] + 0x1104), ==, 0);
    g_assert_cmphex(qtest_readb(q, hosts[0] + 0x19), ==, 0);
    qtest_quit(q);
}

static void mdio_write(QTestState *q, uint64_t h, unsigned reg, unsigned val)
{
    qtest_writel(q, h + 0x1100, reg);
    qtest_writel(q, h + 0x1104, 0x80000000 | val);
    g_assert_cmphex(qtest_readl(q, h + 0x1104) >> 31, ==, 1);
    qtest_clock_step(q, 1000);
    g_assert_cmphex(qtest_readl(q, h + 0x1104), ==, val);
}

static unsigned mdio_read(QTestState *q, uint64_t h, unsigned reg)
{
    qtest_writel(q, h + 0x1100, (1 << 20) | reg);
    g_assert_cmphex(qtest_readl(q, h + 0x1108), ==, 0);
    qtest_clock_step(q, 1000);
    g_assert_cmphex(qtest_readl(q, h + 0x1108) >> 31, ==, 1);
    return qtest_readl(q, h + 0x1108) & 0xffff;
}

static void test_native_mdio(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on "
                              "-m 512M -nodefaults");
    const uint64_t h = 0x1000120000ULL;
    const unsigned regs[] = { 0x16, 0x17, 0x18, 0x19, 0x1b, 0x1c, 0x1e };
    const unsigned values[] = {
        0x50b9, 0xbda1, 0x94, 0x97b4, 0x5030, 0x5030, 7
    };
    unsigned i;

    mdio_write(q, h, 0x1f, 0x1100);
    g_assert_cmphex(mdio_read(q, h, 1), ==, 0); /* not configured */
    mdio_write(q, h, 0x1f, 0x1600);
    g_assert_cmphex(mdio_read(q, h, 0x1f), ==, 0x1600);
    for (i = 0; i < ARRAY_SIZE(regs); i++) {
        mdio_write(q, h, regs[i], values[i]);
        g_assert_cmphex(mdio_read(q, h, regs[i]), ==, values[i]);
    }
    mdio_write(q, h, 0x1f, 0x1100);
    g_assert_cmphex(mdio_read(q, h, 1), ==, 0x800);
    mdio_write(q, h, 2, 0xc000);
    g_assert_cmphex(mdio_read(q, h, 1), ==, 0xc00);
    /* PLL descriptor state does not imply a trained downstream link. */
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
    /* Invalid port is not acknowledged; status writes cannot complete it. */
    qtest_writel(q, h + 0x1100, (1 << 20) | (1 << 16) | 1);
    qtest_writel(q, h + 0x1108, 0xffffffff);
    qtest_clock_step(q, 1000000);
    g_assert_cmphex(qtest_readl(q, h + 0x1108), ==, 0);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    mdio_write(q, h, 0x1f, 0x1100);
    g_assert_cmphex(mdio_read(q, h, 1), ==, 0);
    /* Reset cancels an in-flight read timer. */
    qtest_writel(q, h + 0x1100, (1 << 20) | 1);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    qtest_clock_step(q, 10000);
    g_assert_cmphex(qtest_readl(q, h + 0x1108), ==, 0);
    qtest_quit(q);
}

static void native_link(QTestState *q, uint64_t h)
{
    const unsigned regs[] = { 0x16, 0x17, 0x18, 0x19, 0x1b, 0x1c, 0x1e };
    const unsigned values[] = {
        0x50b9, 0xbda1, 0x94, 0x97b4, 0x5030, 0x5030, 7
    };
    unsigned i;

    qtest_writel(q, h + 0x9210, 0);
    mdio_write(q, h, 0x1f, 0x1600);
    for (i = 0; i < ARRAY_SIZE(regs); i++) {
        mdio_write(q, h, regs[i], values[i]);
    }
    qtest_writel(q, h + 0x4064, 4);
    qtest_clock_step(q, 1000000);
}

static void native_out(QTestState *q, uint64_t h, uint64_t cpu,
                       uint64_t pci, uint64_t size)
{
    qtest_writel(q, h + 0x400c, pci);
    qtest_writel(q, h + 0x4010, pci >> 32);
    qtest_writel(q, h + 0x4070, ((cpu >> 16) & 0xfff0) |
                 ((cpu + size - 1) & 0xfff00000));
    qtest_writel(q, h + 0x4080, cpu >> 32);
    qtest_writel(q, h + 0x4084, (cpu + size - 1) >> 32);
}

static void test_native_rp1(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on "
                              "-m 512M -nodefaults");
    uint64_t h = 0x1000120000ULL, e = 0x1000110000ULL;
    uint64_t data = h + 0x8000, cpu = CM5_RP1_WINDOW;

    qtest_writel(q, h + 0x9000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, data), ==, UINT32_MAX);
    native_link(q, h);
    native_link(q, e); /* no endpoint: never a successful link */
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0xb0);
    g_assert_cmphex(qtest_readl(q, e + 0x4068), ==, 0x80);
    qtest_writel(q, h + 0x18, 0x00010100);
    g_assert_cmphex(qtest_readl(q, data), ==, 0x00011de4);
    qtest_writel(q, h + 0x9000, (1 << 20) | (1 << 15));
    g_assert_cmphex(qtest_readl(q, data), ==, UINT32_MAX);
    qtest_writel(q, h + 0x9000, 1 << 20);
    qtest_writel(q, data + 0x10, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, data + 0x10), ==, 0xffffc000);
    qtest_writel(q, data + 0x14, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, data + 0x14), ==, 0xffc00000);
    qtest_writel(q, data + 0x18, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, data + 0x18), ==, 0xffff0000);
    qtest_writel(q, data + 0x10, 0x410000);
    qtest_writel(q, data + 0x14, 0);
    qtest_writel(q, data + 0x18, 0x400000);
    qtest_writew(q, data + 4, 6);
    qtest_writew(q, h + 4, 6);
    qtest_writel(q, h + 0x20, 0x00f00000); /* 0..16MiB bridge window */
    native_out(q, h, cpu, 0, 16 * 1024 * 1024);
    g_assert_cmphex(qtest_readl(q, cpu), ==, 0x20001927);
    qtest_writel(q, data + 0x14, 0x800000); /* relocate BAR1 */
    g_assert_cmphex(qtest_readl(q, cpu + 0x800000), ==, 0x20001927);
    g_assert_cmphex(qtest_readl(q, cpu), !=, 0x20001927);
    qtest_writel(q, data + 0x14, 0);
    qtest_writel(q, cpu + 0x400000, 0xabcdef12);
    g_assert_cmphex(qtest_readl(q, cpu + 0x400000), ==, 0xabcdef12);
    /* BAR relocation, bridge decode, and outbound translation are distinct. */
    qtest_writel(q, data + 0x18, 0x600000);
    g_assert_cmphex(qtest_readl(q, cpu + 0x600000), ==, 0xabcdef12);
    g_assert_cmphex(qtest_readl(q, cpu + 0x400000), !=, 0xabcdef12);
    native_out(q, h, cpu + 0x1000000, 0, 16 * 1024 * 1024);
    g_assert_cmphex(qtest_readl(q, cpu), !=, 0x20001927);
    g_assert_cmphex(qtest_readl(q, cpu + 0x1000000), ==, 0x20001927);
    qtest_writew(q, h + 4, 0);
    g_assert_cmphex(qtest_readl(q, cpu + 0x1000000), !=, 0x20001927);
    qtest_writew(q, h + 4, 6);
    qtest_writeb(q, h + 0x19, 2);
    qtest_writeb(q, h + 0x1a, 2);
    g_assert_cmphex(qtest_readl(q, data), ==, UINT32_MAX);
    qtest_writel(q, h + 0x9000, 2 << 20);
    g_assert_cmphex(qtest_readl(q, data), ==, 0x00011de4);
    /* Window ends and a 64-bit CPU aperture use the same decoder. */
    native_out(q, h, 0x1c00000000ULL, 0, 16 * 1024 * 1024);
    g_assert_cmphex(qtest_readl(q, 0x1c00000000ULL), ==, 0x20001927);
    g_assert_cmphex(qtest_readl(q, 0x1c01000000ULL), !=, 0x20001927);
    native_out(q, h, 0x1c00000000ULL, UINT64_MAX - 3, 0x100000);
    g_assert_cmphex(qtest_readq(q, 0x1c00000000ULL), !=, 0x20001927);
    native_out(q, h, 0x1c00000000ULL, 0, 16 * 1024 * 1024);
    qtest_writew(q, h + 0x3e, 0x40); /* secondary bus reset */
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
    qtest_writew(q, h + 0x3e, 0);
    qtest_clock_step(q, 1000000);
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0xb0);
    qtest_writew(q, h + 0xbc, 0x10); /* link disable */
    g_assert_cmphex(qtest_readw(q, h + 0xbe), ==, 0);
    qtest_writew(q, h + 0xbc, 0);
    qtest_clock_step(q, 1000000);
    qtest_writel(q, h + 0x4064, 0);
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
    g_assert_cmphex(qtest_readl(q, data), ==, UINT32_MAX);
    qtest_writel(q, h + 0x4064, 4);
    qtest_clock_step(q, 999999);
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0xb0);
    g_assert_cmphex(qtest_readl(q, data + 0x18), ==, 0); /* endpoint reset */
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    g_assert_cmphex(qtest_readl(q, h + 0x4068), ==, 0x80);
    qtest_quit(q);
}

static void test_native_msi(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on "
                              "-m 512M -nodefaults "
                              "-device ssi-test-slave,bus=spi,cs=0");
    uint64_t h = 0x1000120000ULL, data = h + 0x8000;
    uint64_t spi = CM5_RP1_WINDOW + 0x50000;
    uint64_t table = CM5_RP1_WINDOW + 0x500000 + 19 * 16;
    uint64_t cfg = CM5_RP1_WINDOW + 0x108008 + 19 * 4;
    unsigned irq = 128 + 19, id = irq + 32;
    uint64_t pending = CM5_GIC_DIST + 0x200 + id / 32 * 4;
    uint32_t bit = 1U << (id % 32);
    unsigned other_id = 247 + 8 + 32;
    uint64_t other_pending = CM5_GIC_DIST + 0x200 + other_id / 32 * 4;
    uint32_t other_bit = 1U << (other_id % 32);

    native_link(q, h);
    qtest_writel(q, h + 0x18, 0x00010100);
    qtest_writew(q, h + 4, 6);
    qtest_writel(q, h + 0x20, 0x00f00000);
    qtest_writel(q, h + 0x9000, 1 << 20);
    qtest_writel(q, data + 0x10, 0x410000);
    qtest_writel(q, data + 0x14, 0);
    qtest_writew(q, data + 4, 6);
    native_out(q, h, CM5_RP1_WINDOW, 0, 16 * 1024 * 1024);
    /* Driver-programmed inbound RAM and per-host MIP windows. */
    qtest_writel(q, h + 0x402c, 14); /* 512MiB */
    qtest_writel(q, h + 0x4030, 0x10);
    qtest_writel(q, h + 0x40ac, 1);
    qtest_writel(q, h + 0x40b0, 0);
    qtest_writel(q, h + 0x4034, 0xfffff01c); /* 4KiB */
    qtest_writel(q, h + 0x4038, 0xff);
    qtest_writel(q, h + 0x40b4, 0x130001);
    qtest_writel(q, h + 0x40b8, 0x10);
    qtest_writel(q, CM5_MIP0 + 0x20, UINT32_MAX);
    qtest_writel(q, CM5_MIP0 + 0x40, 0);
    qtest_writel(q, CM5_GIC_DIST + 0xc00 + id / 16 * 4, 0xaaaaaaaa);
    qtest_writeb(q, CM5_GIC_DIST + 0x800 + id, 1);
    qtest_writel(q, data + 0x10, 0x500000); /* relocate BAR0 */
    qtest_writel(q, table, (uint32_t)CM5_MIP_MSI);
    qtest_writel(q, table + 4, CM5_MIP_MSI >> 32);
    qtest_writel(q, table + 8, 19);
    qtest_writel(q, table + 12, 1); /* MSI-X masked */
    qtest_writew(q, data + 0xb2, 0x8000 | 60);
    qtest_writel(q, cfg, 9); /* RP1 level IRQ, explicit ACK rearm */
    qtest_writel(q, spi + 8, 1);
    qtest_writel(q, spi + 0x2c, 1); /* real SSI TX-empty event */
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_WINDOW + 0x501000) & (1 << 19),
                    ==, 1 << 19);
    qtest_writel(q, table + 12, 0);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_WINDOW + 0x501000) & (1 << 19),
                    ==, 0);
    qtest_writel(q, pending + 0x80, bit);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_writel(q, cfg, 13); /* ACK an asserted source: another edge */
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    qtest_writel(q, pending + 0x80, bit);
    qtest_writel(q, CM5_MIP0 + 0x40, 1 << 19);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_writel(q, CM5_MIP0 + 0x40, 0);
    qtest_writew(q, data + 4, 2); /* endpoint bus mastering disabled */
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_writew(q, data + 4, 6);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    qtest_writel(q, pending + 0x80, bit);
    qtest_writel(q, table, (uint32_t)CM5_MIP_MSI + 4); /* invalid doorbell */
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_writel(q, table, (uint32_t)CM5_MIP_MSI);
    qtest_writel(q, h + 0x40b4, 0x131001); /* other host MIP: isolated */
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    /* Make the other MIP a live target with valid data, not a masked oracle. */
    qtest_writel(q, CM5_MIP1 + 0x20, UINT32_MAX);
    qtest_writel(q, CM5_MIP1 + 0x40, 0);
    qtest_writel(q, CM5_GIC_DIST + 0xc00 + other_id / 16 * 4, 0xaaaaaaaa);
    qtest_writeb(q, CM5_GIC_DIST + 0x800 + other_id, 1);
    qtest_writel(q, CM5_MIP1, 8); /* positive control for the observer */
    g_assert_cmphex(qtest_readl(q, other_pending) & other_bit, ==, other_bit);
    qtest_writel(q, other_pending + 0x80, other_bit);
    qtest_writel(q, table + 8, 8);
    qtest_writel(q, cfg, 13); /* this endpoint still cannot reach other MIP */
    g_assert_cmphex(qtest_readl(q, other_pending) & other_bit, ==, 0);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_writel(q, table + 8, 19);
    qtest_writel(q, h + 0x40b4, 0x130001);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    /* The same endpoint DMA path can reach translated RAM, not identity RAM. */
    qtest_writel(q, table, 0x1000);
    qtest_writel(q, table + 4, 0x10);
    qtest_writel(q, table + 8, 0x12345678);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, 0x1000), ==, 0x12345678);
    qtest_writel(q, table, 0x1ffffffc); /* last valid RAM word */
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, 0x1ffffffc), ==, 0x12345678);
    qtest_writel(q, table, 0x20000000); /* exact-end address rejected */
    qtest_writel(q, table + 8, 0xabcdef00);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, 0x1ffffffc), ==, 0x12345678);
    qtest_writel(q, table, 0x1000);
    qtest_writel(q, h + 0x40ac, 0); /* inbound RAM decode disabled */
    qtest_writel(q, table + 8, 0xabcdef00);
    qtest_writel(q, cfg, 13);
    g_assert_cmphex(qtest_readl(q, 0x1000), ==, 0x12345678);
    /* Phase 10H: PERST cancels a masked event and the next active frame. */
    qtest_writel(q, table, (uint32_t)CM5_MIP_MSI);
    qtest_writel(q, table + 4, CM5_MIP_MSI >> 32);
    qtest_writel(q, table + 8, 19);
    qtest_writel(q, table + 12, 1);
    qtest_writel(q, spi + 8, 0);
    qtest_writel(q, spi, 7 << 16);
    qtest_writel(q, spi + 0x14, 200);
    qtest_writel(q, spi + 0x10, 1);
    qtest_writel(q, spi + 0x2c, 0x10);
    qtest_writel(q, spi + 8, 1);
    qtest_writel(q, cfg, 13);
    qtest_writel(q, spi + 0x60, 0x12);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_WINDOW + 0x501000), ==, 1 << 19);
    qtest_writel(q, spi + 0x60, 0x34);
    /* Endpoint reset cannot retract an edge already latched by the GIC. */
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    qtest_writel(q, h + 0x4064, 0); /* PERST resets endpoint IRQ/MSI state */
    g_assert_cmphex(qtest_readw(q, data + 0xb2), ==, 0xffff);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    qtest_writel(q, pending + 0x80, bit);
    qtest_writel(q, h + 0x4064, 4);
    qtest_clock_step(q, 1000000);
    qtest_writel(q, data + 0x10, 0x500000);
    qtest_writel(q, data + 0x14, 0);
    qtest_writew(q, data + 4, 6);
    g_assert_cmphex(qtest_readl(q, CM5_RP1_WINDOW + 0x501000), ==, 0);
    g_assert_cmphex(qtest_readl(q, spi + 0x24), ==, 0);
    g_assert_cmphex(qtest_readl(q, spi + 0x28), ==, 6);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    g_assert_cmphex(qtest_readl(q, CM5_MIP0 + 0x40), ==, UINT32_MAX);
    qtest_quit(q);
}

static void test_native_clock(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on "
                              "-m 512M -nodefaults "
                              "-device ssi-test-slave,bus=spi,cs=0");
    uint64_t h = 0x1000120000ULL, data = h + 0x8000;
    uint64_t cpu = CM5_RP1_WINDOW, spi = cpu + 0x50000;

    native_link(q, h);
    g_assert_cmphex(qtest_readw(q, h + 0xbe) & 0x3ff, ==, 0x42);
    qtest_writel(q, h + 0x18, 0x00010100);
    qtest_writew(q, h + 4, 6);
    qtest_writel(q, h + 0x20, 0x00f00000);
    qtest_writel(q, h + 0x9000, 1 << 20);
    qtest_writel(q, data + 0x14, 0);
    qtest_writew(q, data + 4, 6);
    native_out(q, h, cpu, 0, 16 * 1024 * 1024);
    g_assert_cmphex(qtest_readl(q, cpu + 0x20000), ==, 0x80000001);
    g_assert_cmphex(qtest_readl(q, cpu + 0x18020), ==, 4);
    qtest_writel(q, cpu + 0x20004, 1); /* PLL power down */
    g_assert_cmphex(qtest_readl(q, cpu + 0x20000), ==, 1);
    g_assert_cmphex(qtest_readl(q, cpu + 0x18020), ==, 0);
    qtest_writel(q, cpu + 0x20000, 0x80000000); /* no refdiv, can't fake lock */
    g_assert_cmphex(qtest_readl(q, cpu + 0x20000), ==, 0);
    qtest_writel(q, cpu + 0x20000, 1);
    qtest_writel(q, cpu + 0x20004, 0);
    g_assert_cmphex(qtest_readl(q, cpu + 0x20000), ==, 0x80000001);
    qtest_writel(q, spi, 7 << 16);
    qtest_writel(q, spi + 0x14, 200);
    qtest_writel(q, spi + 0x10, 1);
    qtest_writel(q, spi + 8, 1);
    qtest_writel(q, cpu + 0x18014, 2); /* clock gate closes */
    qtest_writel(q, spi + 0x60, 0x72);
    qtest_clock_step(q, 1000000);
    g_assert_cmphex(qtest_readl(q, spi + 0x20), ==, 1);
    g_assert_cmphex(qtest_readl(q, spi + 0x24), ==, 0);
    qtest_writel(q, cpu + 0x18014, 0x802);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, spi + 0x60), ==, 0x72 ^ 0xa5);
    qtest_writel(q, spi + 0x60, 0x35);
    qtest_clock_step(q, 4000);
    qtest_writel(q, cpu + 0x18014, 2); /* pause an in-flight word */
    qtest_clock_step(q, 100000);
    g_assert_cmpuint(qtest_readl(q, spi + 0x24), ==, 0);
    g_assert_cmphex(qtest_readl(q, spi + 0x28) & 1, ==, 1);
    qtest_writel(q, cpu + 0x18014, 0x802);
    qtest_clock_step(q, 3999);
    g_assert_cmpuint(qtest_readl(q, spi + 0x24), ==, 0);
    qtest_clock_step(q, 1); /* only the unshifted half remains */
    g_assert_cmpuint(qtest_readl(q, spi + 0x24), ==, 1);
    g_assert_cmphex(qtest_readl(q, spi + 0x60), ==, 0x35 ^ 0xa5);
    qtest_writel(q, spi + 0x60, 0x56);
    qtest_clock_step(q, 2000); /* one quarter at 200MHz */
    qtest_writel(q, cpu + 0x18018, 2); /* remaining clocks at 100MHz */
    qtest_clock_step(q, 11999);
    g_assert_cmpuint(qtest_readl(q, spi + 0x24), ==, 0);
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, spi + 0x60), ==, 0x56 ^ 0xa5);
    qtest_writel(q, cpu + 0x18018, 1);
    qtest_writel(q, cpu + 0x18014, 0x803); /* unsupported parent */
    g_assert_cmphex(qtest_readl(q, cpu + 0x18020), ==, 0);
    qtest_writel(q, h + 0x4064, 0);
    qtest_writel(q, h + 0x4064, 4);
    qtest_clock_step(q, 1000000);
    qtest_writel(q, data + 0x14, 0);
    qtest_writew(q, data + 4, 6);
    g_assert_cmphex(qtest_readl(q, cpu + 0x18014), ==, 0x802);
    qtest_quit(q);
}

static void test_native_gpio(void)
{
    QTestState *q = qtest_init("-M cm5io-dev,native-pcie=on,native-mip=on,"
        "rp1-gpio-lab=on -m 512M -nodefaults");
    uint64_t h = 0x1000120000ULL, cfg = h + 0x8000;
    uint64_t io = CM5_RP1_WINDOW + 0xd0000;
    uint64_t rio = CM5_RP1_WINDOW + 0xe0000;
    uint64_t pads = CM5_RP1_WINDOW + 0xf0000;
    uint64_t table = CM5_RP1_WINDOW + 0x500000;
    uint64_t irqcfg = CM5_RP1_WINDOW + 0x108008;
    unsigned id = 128 + 32;
    uint64_t pending = CM5_GIC_DIST + 0x200 + id / 32 * 4;
    uint32_t bit = 1U << (id % 32);

    native_link(q, h);
    qtest_writel(q, h + 0x18, 0x00010100);
    qtest_writew(q, h + 4, 6);
    qtest_writel(q, h + 0x20, 0x00f00000);
    qtest_writel(q, h + 0x9000, 1 << 20);
    qtest_writel(q, cfg + 0x10, 0x500000);
    qtest_writel(q, cfg + 0x14, 0);
    qtest_writew(q, cfg + 4, 6);
    native_out(q, h, CM5_RP1_WINDOW, 0, 16 * 1024 * 1024);
    qtest_writel(q, h + 0x4034, 0xfffff01c);
    qtest_writel(q, h + 0x4038, 0xff);
    qtest_writel(q, h + 0x40b4, 0x130001);
    qtest_writel(q, h + 0x40b8, 0x10);
    qtest_writel(q, CM5_MIP0 + 0x20, UINT32_MAX);
    qtest_writel(q, CM5_MIP0 + 0x40, 0);
    qtest_writel(q, CM5_GIC_DIST + 0xc00 + id / 16 * 4, 0xaaaaaaaa);
    qtest_writeb(q, CM5_GIC_DIST + 0x800 + id, 1);
    qtest_writel(q, table, CM5_MIP_MSI);
    qtest_writel(q, table + 4, CM5_MIP_MSI >> 32);
    qtest_writel(q, table + 8, 0);
    qtest_writel(q, table + 12, 0);
    qtest_writew(q, cfg + 0xb2, 0x8000 | 60);
    qtest_writel(q, irqcfg, 9);
    qtest_writel(q, pads + 84, 0x52);
    qtest_writel(q, pads + 88, 0x52);
    qtest_writel(q, io + 164, 0x85);
    qtest_writel(q, io + 172, 0x85 | (1 << 21));
    qtest_writel(q, rio + 0x2004, 1 << 20);
    qtest_writel(q, io + 0x211c, 1 << 21);
    qtest_writel(q, rio + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    g_assert_cmphex(qtest_readl(q, io + 0x124), ==, 1 << 21);
    qtest_writel(q, io + 172 + 0x2000, 1 << 28);
    qtest_writel(q, irqcfg + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    qtest_writel(q, pending + 0x80, bit);
    qtest_writel(q, table + 12, 1);
    qtest_writel(q, rio + 0x3000, 1 << 20);
    qtest_writel(q, rio + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, table + 0x1000), ==, 1);
    qtest_writel(q, h + 0x4064, 0); /* reset with masked GPIO event */
    qtest_writel(q, h + 0x4064, 4);
    qtest_clock_step(q, 1000000);
    qtest_writel(q, cfg + 0x10, 0x500000);
    qtest_writel(q, cfg + 0x14, 0);
    qtest_writew(q, cfg + 4, 6);
    g_assert_cmphex(qtest_readl(q, table + 0x1000), ==, 0);
    g_assert_cmphex(qtest_readl(q, io + 172), ==, 0x9f);
    g_assert_cmphex(qtest_readl(q, rio + 4), ==, 0);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    qtest_quit(q);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/cm5io-dev/board-rp1-spi-reset", test_machine);
    qtest_add_func("/cm5io-dev/optional-connectors", test_options);
    qtest_add_func("/cm5io-dev/native-pcie-probe-boundary", test_native_probe);
    qtest_add_func("/cm5io-dev/native-mdio-transactions-reset-invalid",
                   test_native_mdio);
    qtest_add_func("/cm5io-dev/native-rp1-config-window-link-reset",
                   test_native_rp1);
    qtest_add_func("/cm5io-dev/native-ssi-msix-inbound-mip", test_native_msi);
    qtest_add_func("/cm5io-dev/native-rp1-clock-pll-gate-reset",
                   test_native_clock);
    qtest_add_func("/cm5io-dev/native-gpio-msix-mip-reset", test_native_gpio);
    return g_test_run();
}

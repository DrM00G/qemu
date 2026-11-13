/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local research: Linux edge-mode MIP and PCI inbound aperture. */
#include "qemu/osdep.h"
#include "hw/arm/cm5io-dev.h"
#include "libqtest.h"

static uint64_t pending_reg(unsigned spi, bool clear)
{
    return CM5_GIC_DIST + (clear ? 0x280 : 0x200) + ((spi + 32) / 32) * 4;
}

static uint32_t pending_bit(unsigned spi)
{
    return 1U << ((spi + 32) % 32);
}

static void edge_irq(QTestState *q, unsigned spi)
{
    unsigned id = spi + 32;
    qtest_writel(q, CM5_GIC_DIST + 0xc00 + id / 16 * 4, 0xaaaaaaaa);
    qtest_writeb(q, CM5_GIC_DIST + 0x800 + id, 1);
}

static void init_mip(QTestState *q, uint64_t base)
{
    /* Exactly the six programming writes made by the public Linux driver. */
    qtest_writel(q, base + 0x40, 0);
    qtest_writel(q, base + 0x50, 0);
    qtest_writel(q, base + 0x60, UINT32_MAX);
    qtest_writel(q, base + 0x70, UINT32_MAX);
    qtest_writel(q, base + 0x20, UINT32_MAX);
    qtest_writel(q, base + 0x30, UINT32_MAX);
}

static QTestState *start(void)
{
    return qtest_init("-M cm5io-dev,native-mip=on -m 512M -nodefaults");
}

static void test_edge_mask_reset(void)
{
    QTestState *q = start();
    const unsigned spi = 128 + 19;
    uint32_t bit = pending_bit(spi);

    edge_irq(q, spi);
    init_mip(q, CM5_MIP0);
    g_assert_cmphex(qtest_readl(q, CM5_MIP0 + 0x20), ==, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, CM5_MIP0 + 0x60), ==, UINT32_MAX);
    qtest_writel(q, CM5_MIP0, 19);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & bit, ==, bit);
    /* The edge has deasserted; parent GIC clear must remove pending state. */
    qtest_writel(q, pending_reg(spi, true), bit);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & bit, ==, 0);
    qtest_writel(q, CM5_MIP0 + 0x40, 1 << 19);
    qtest_writel(q, CM5_MIP0, 19);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & bit, ==, 0);
    qtest_writel(q, CM5_MIP0 + 0x40, 0);
    qtest_writel(q, CM5_MIP0, 19);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & bit, ==, bit);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    /* Conservative model reset, explicitly not a silicon reset claim. */
    g_assert_cmphex(qtest_readl(q, CM5_MIP0 + 0x40), ==, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, CM5_MIP0 + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & bit, ==, 0);
    qtest_quit(q);
}

static void test_ranges(void)
{
    QTestState *q = start();
    unsigned spi0 = 128 + 40, spi1 = 247 + 8;

    init_mip(q, CM5_MIP0);
    init_mip(q, CM5_MIP1);
    edge_irq(q, spi0);
    edge_irq(q, spi1);
    qtest_writel(q, CM5_MIP0, 40);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi0, false)) &
                    pending_bit(spi0),
                    ==, pending_bit(spi0));
    qtest_writel(q, CM5_MIP1, 7); /* below MIP1's published offset */
    qtest_writel(q, CM5_MIP1, 16); /* above its eight-vector range */
    qtest_writel(q, CM5_MIP0, 64);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi1, false)) &
                    pending_bit(spi1),
                    ==, 0);
    qtest_writel(q, CM5_MIP1, 8);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi1, false)) &
                    pending_bit(spi1),
                    ==, pending_bit(spi1));
    qtest_quit(q);
}

static void test_pcie_aperture(void)
{
    QTestState *q = start();
    const uint64_t config = CM5_RP1_ECAM + 0x8000;
    const uint64_t table = CM5_RP1_WINDOW + 0x400000 + 19 * 16;
    const unsigned spi = 128 + 19;

    init_mip(q, CM5_MIP0);
    edge_irq(q, spi);
    qtest_writel(q, config + 0x10, CM5_PCI_BUS_BASE + 0x400000);
    qtest_writel(q, config + 0x14, CM5_PCI_BUS_BASE);
    qtest_writew(q, config + 4, 6);
    qtest_writel(q, table, (uint32_t)CM5_MIP_MSI);
    qtest_writel(q, table + 4, CM5_MIP_MSI >> 32);
    qtest_writel(q, table + 8, 19);
    qtest_writel(q, table + 12, 0);
    qtest_writew(q, config + 0xb2, 0x8000 | 60);
    /* RP1 test IRQ -> MSI-X -> PCI bus alias -> MIP0 -> GIC, not CPU alias. */
    qtest_writel(q, CM5_RP1_WINDOW + 0x108008 + 19 * 4, 3);
    g_assert_cmphex(qtest_readl(q, pending_reg(spi, false)) & pending_bit(spi),
                    ==, pending_bit(spi));
    qtest_quit(q);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/bcm2712-mip/edge-mask-gic-clear-reset",
                   test_edge_mask_reset);
    qtest_add_func("/bcm2712-mip/vector-ranges-offset", test_ranges);
    qtest_add_func("/bcm2712-mip/rp1-pcie-inbound-msi", test_pcie_aperture);
    return g_test_run();
}

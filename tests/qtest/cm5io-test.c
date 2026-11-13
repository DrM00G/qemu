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

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/cm5io-dev/board-rp1-spi-reset", test_machine);
    qtest_add_func("/cm5io-dev/optional-connectors", test_options);
    return g_test_run();
}

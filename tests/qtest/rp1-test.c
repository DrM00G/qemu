/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Local RP1 research qtests. AI-assisted, not for upstream submission. */
#include "qemu/osdep.h"
#include "libqtest.h"

#define ECAM 0x3f008000ULL /* virt,highmem=off, PCI slot 1 */
#define BAR0 0x10400000ULL
#define BAR1 0x10000000ULL
#define SPI (BAR1 + 0x50000)
#define IRQCFG (BAR1 + 0x108008 + 19 * 4)
#define MESSAGE 0x40001000ULL

static void assign_bars(QTestState *q)
{
    qtest_writel(q, ECAM + 0x10, BAR0);
    qtest_writel(q, ECAM + 0x14, BAR1);
    qtest_writew(q, ECAM + 4, 6);
}

static QTestState *start(void)
{
    QTestState *q = qtest_init("-machine virt,highmem=off -nodefaults "
                             "-device rp1-pci,id=rp1,addr=1 "
                             "-device ssi-test-slave,bus=spi,cs=0");
    assign_bars(q);
    return q;
}

static void setup_spi(QTestState *q)
{
    qtest_writel(q, SPI + 8, 0);
    qtest_writel(q, SPI, 7 << 16);
    qtest_writel(q, SPI + 0x14, 200); /* 1 MHz */
    qtest_writel(q, SPI + 0x2c, 0);
    qtest_writel(q, SPI + 0x10, 1);
    qtest_writel(q, SPI + 8, 1);
}

static void test_pci(void)
{
    QTestState *q = start();
    unsigned cap = qtest_readb(q, ECAM + 0x34);
    bool found = false;

    g_assert_cmphex(qtest_readl(q, ECAM), ==, 0x00011de4);
    qtest_writel(q, ECAM + 0x10, 0xffffffff);
    g_assert_cmphex(qtest_readl(q, ECAM + 0x10), ==, 0xffffc000);
    qtest_writel(q, ECAM + 0x14, 0xffffffff);
    g_assert_cmphex(qtest_readl(q, ECAM + 0x14), ==, 0xffc00000);
    assign_bars(q);
    while (cap) {
        if (qtest_readb(q, ECAM + cap) == 0x11) {
            g_assert_cmpuint(qtest_readw(q, ECAM + cap + 2) & 0x7ff, ==, 60);
            found = true;
        }
        cap = qtest_readb(q, ECAM + cap + 1);
    }
    g_assert_true(found);
    g_assert_cmphex(qtest_readl(q, BAR1), ==, 0x20001927);
    g_assert_cmphex(qtest_readl(q, SPI + 0x5c), ==, 0x3430322a);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28), ==, 6);
    g_assert_cmphex(qtest_readl(q, SPI + 8), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x2c), ==, 0x3f);
    qtest_quit(q);
}

static void test_transfer(void)
{
    QTestState *q = start();
    const uint8_t tx[] = { 0x10, 0x20, 0x30, 0x40 };
    unsigned i;

    setup_spi(q);
    /* Queue with CS disabled: no shift until SER selects a peripheral. */
    qtest_writel(q, SPI + 0x10, 0);
    for (i = 0; i < ARRAY_SIZE(tx); i++) {
        qtest_writel(q, SPI + 0x60, tx[i]);
    }
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 4);
    qtest_clock_step(q, 1000000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    qtest_writel(q, SPI + 0x10, 1);
    for (i = 0; i < ARRAY_SIZE(tx); i++) {
        qtest_clock_step(q, 8000);
    }
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 4);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28), ==, 0xe);
    for (i = 0; i < ARRAY_SIZE(tx); i++) {
        g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, tx[i] ^ 0xa5);
    }
    /* CS1 has no slave and must not select the CS0 fixture. */
    qtest_writel(q, SPI + 0x10, 2);
    qtest_writel(q, SPI + 0x60, 0x55);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0);
    qtest_quit(q);
}

static void test_errors_reset(void)
{
    QTestState *q = start();
    unsigned i;

    /* Disabled DR writes have no effect. */
    qtest_writel(q, SPI + 0x60, 0x55);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    setup_spi(q);
    qtest_writel(q, SPI + 0x10, 0);
    for (i = 0; i < 65; i++) {
        qtest_writel(q, SPI + 0x60, i);
    }
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 64);
    g_assert_cmphex(qtest_readl(q, SPI + 0x34) & 2, ==, 2);
    g_assert_cmphex(qtest_readl(q, SPI + 0x38), ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x34) & 2, ==, 0);
    qtest_readl(q, SPI + 0x60);
    g_assert_cmphex(qtest_readl(q, SPI + 0x34) & 4, ==, 4);
    qtest_readl(q, SPI + 0x40);
    g_assert_cmphex(qtest_readl(q, SPI + 0x34) & 4, ==, 0);
    /* Reset with a pending timer must cancel the transfer. */
    qtest_writel(q, SPI + 0x10, 1);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    assign_bars(q);
    qtest_clock_step(q, 1000000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmpuint(qtest_readl(q, SPI + 8), ==, 0);
    qtest_quit(q);
}

static void test_msix(void)
{
    QTestState *q = start();
    const uint64_t table = BAR0 + 19 * 16;

    setup_spi(q);
    qtest_writel(q, table, MESSAGE);
    qtest_writel(q, table + 4, 0);
    qtest_writel(q, table + 8, 0x12345678);
    qtest_writel(q, table + 12, 0); /* unmask vector */
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    qtest_writel(q, IRQCFG + 0x800, 9); /* enable + IACK_EN */
    qtest_writel(q, SPI + 0x2c, 0x10); /* RX threshold IRQ */
    qtest_writel(q, SPI + 0x60, 0x10);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30), ==, 0x10);
    g_assert_cmphex(qtest_readl(q, BAR1 + 0x108108), ==, 1 << 19);
    /* Unserviced level must retrigger on IACK. */
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_readl(q, SPI + 0x60);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30), ==, 0);
    /* Masked vector sets PBA; unmask delivers the pending message. */
    qtest_writel(q, table + 12, 1);
    qtest_writel(q, SPI + 0x60, 0x20);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 1 << 19);
    qtest_writel(q, table + 12, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_quit(q);
}

static void test_config_overflow(void)
{
    QTestState *q = start();
    const unsigned widths[] = { 4, 16, 32 };
    unsigned i, j;

    for (i = 0; i < ARRAY_SIZE(widths); i++) {
        unsigned bits = widths[i];
        uint32_t mask = bits == 32 ? UINT32_MAX : (1U << bits) - 1;

        setup_spi(q);
        qtest_writel(q, SPI + 8, 0);
        qtest_writel(q, SPI, ((bits - 1) << 16) | 0xc0);
        qtest_writel(q, SPI + 8, 1);
        qtest_writel(q, SPI + 0x60, 0x12345678);
        qtest_clock_step(q, bits * 1000);
        g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==,
                        (0x12345678 ^ 0xa5) & mask);
    }
    setup_spi(q);
    /* Threshold registers only implement log2(FIFO depth) bits. */
    qtest_writel(q, SPI + 0x18, 63);
    qtest_writel(q, SPI + 0x18, 64);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x18), ==, 0);
    for (i = 0; i < 64; i++) {
        qtest_writel(q, SPI + 0x60, i);
    }
    for (i = 0; i < 64; i++) {
        qtest_clock_step(q, 8000);
    }
    qtest_writel(q, SPI + 0x60, 0xff);
    qtest_clock_step(q, 8000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 64);
    g_assert_cmphex(qtest_readl(q, SPI + 0x34) & 8, ==, 8);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x3c), ==, 1);
    for (j = 0; j < 64; j++) {
        g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, j ^ 0xa5);
    }
    /* Transmit-only shifts on SSI but does not fill RX FIFO. */
    qtest_writel(q, SPI + 8, 0);
    qtest_writel(q, SPI, (7 << 16) | (1 << 8));
    qtest_writel(q, SPI + 8, 1);
    qtest_writel(q, SPI + 0x60, 0x55);
    qtest_clock_step(q, 8000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    /* Zero baud divisor cannot clock a transfer. Disable flushes it. */
    qtest_writel(q, SPI + 8, 0);
    qtest_writel(q, SPI + 0x14, 0);
    qtest_writel(q, SPI + 8, 1);
    qtest_writel(q, SPI + 0x60, 0x55);
    qtest_clock_step(q, 1000000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 1);
    qtest_writel(q, SPI + 8, 0);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    qtest_quit(q);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/rp1/pci-reset-registers", test_pci);
    qtest_add_func("/rp1/spi-transfer-cs", test_transfer);
    qtest_add_func("/rp1/fifo-errors-reset", test_errors_reset);
    qtest_add_func("/rp1/msix-level-ack-mask", test_msix);
    qtest_add_func("/rp1/frame-config-rx-overflow", test_config_overflow);
    return g_test_run();
}

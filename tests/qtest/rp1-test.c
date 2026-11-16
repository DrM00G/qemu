/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Local RP1 research qtests. AI-assisted, not for upstream submission. */
#include "qemu/osdep.h"
#include "libqtest.h"

#define ECAM 0x3f008000ULL /* virt,highmem=off, PCI slot 1 */
#define BAR0 0x10400000ULL
#define BAR1 0x10000000ULL
#define BAR2 0x10410000ULL
#define SPI (BAR1 + 0x50000)
#define IRQCFG (BAR1 + 0x108008 + 19 * 4)
#define MESSAGE 0x40001000ULL

static void assign_bars(QTestState *q)
{
    qtest_writel(q, ECAM + 0x10, BAR0);
    qtest_writel(q, ECAM + 0x14, BAR1);
    qtest_writel(q, ECAM + 0x18, BAR2);
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

static void test_bar2(void)
{
    QTestState *q = start();
    const uint64_t relocated = 0x10500000;
    uint8_t contents[65536];
    unsigned i;

    qtest_writel(q, ECAM + 0x18, 0xffffffff);
    g_assert_cmphex(qtest_readl(q, ECAM + 0x18), ==, 0xffff0000);
    assign_bars(q);
    qtest_writeb(q, BAR2, 0xa5);
    qtest_writew(q, BAR2 + 2, 0x1234);
    qtest_writel(q, BAR2 + 65532, 0x89abcdef);
    g_assert_cmphex(qtest_readb(q, BAR2), ==, 0xa5);
    g_assert_cmphex(qtest_readw(q, BAR2 + 2), ==, 0x1234);
    g_assert_cmphex(qtest_readl(q, BAR2 + 65532), ==, 0x89abcdef);
    g_assert_cmphex(qtest_readl(q, BAR2 + 65536), ==, 0xffffffff);
    qtest_writel(q, ECAM + 0x18, relocated);
    g_assert_cmphex(qtest_readl(q, BAR2), ==, 0xffffffff);
    g_assert_cmphex(qtest_readl(q, relocated + 65532), ==, 0x89abcdef);
    qtest_writew(q, ECAM + 4, 0);
    g_assert_cmphex(qtest_readl(q, relocated), ==, 0xffffffff);
    qtest_writew(q, ECAM + 4, 6);
    g_assert_cmphex(qtest_readb(q, relocated), ==, 0xa5);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    assign_bars(q);
    qtest_memread(q, BAR2, contents, sizeof(contents));
    for (i = 0; i < sizeof(contents); i++) {
        g_assert_cmpuint(contents[i], ==, 0);
    }
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

static void test_shift_pipeline(void)
{
    QTestState *q = start();

    setup_spi(q);
    qtest_writel(q, SPI + 0x2c, 1); /* TX FIFO empty interrupt */
    qtest_writel(q, SPI + 0x60, 0x12);
    /* FIFO empty and BUSY are independent while the word is shifting. */
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 5, ==, 5);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30) & 1, ==, 1);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    /* Refill during the in-flight word, before the first frame ends. */
    qtest_clock_step(q, 4000);
    qtest_writel(q, SPI + 0x60, 0x34);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30) & 1, ==, 0);
    qtest_clock_step(q, 3999);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    qtest_clock_step(q, 1);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 1);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 1, ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30) & 1, ==, 1);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 1, ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x34 ^ 0xa5);
    qtest_writel(q, SPI + 0x60, 0x56);
    qtest_clock_step(q, 4000);
    qtest_writel(q, SPI + 8, 0); /* disable aborts the in-flight word */
    qtest_clock_step(q, 10000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 1, ==, 0);
    qtest_quit(q);
}

static void test_queued_frame_periods(void)
{
    QTestState *q = start();
    unsigned i;

    setup_spi(q);
    qtest_writel(q, SPI + 0x10, 0);
    for (i = 0; i < 4; i++) {
        qtest_writel(q, SPI + 0x60, i);
    }
    qtest_writel(q, SPI + 0x10, 1);
    /* Advance four scheduled frame periods with four queued words. */
    qtest_clock_step(q, 32000);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 4);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 1, ==, 0);
    for (i = 0; i < 4; i++) {
        g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, i ^ 0xa5);
    }
    qtest_quit(q);
}

static void test_drain_refill(void)
{
    QTestState *q = start();

    setup_spi(q);
    qtest_writel(q, SPI + 0x2c, 1);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 8000);
    /* A genuine empty completion must be idle, with TX-empty IRQ pending. */
    g_assert_cmphex(qtest_readl(q, SPI + 0x28), ==, 0xe);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x30), ==, 1);
    qtest_clock_step(q, 1);
    qtest_writel(q, SPI + 0x60, 0x34);
    qtest_clock_step(q, 7999);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 1);
    qtest_clock_step(q, 1);
    g_assert_cmpuint(qtest_readl(q, SPI + 0x24), ==, 2);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x34 ^ 0xa5);
    qtest_quit(q);
}

static void test_reset_pending_msix(void)
{
    QTestState *q = start();
    const uint64_t table = BAR0 + 19 * 16;

    setup_spi(q);
    qtest_writel(q, table, MESSAGE);
    qtest_writel(q, table + 8, 0x12345678);
    qtest_writel(q, table + 12, 1); /* masked */
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    qtest_writel(q, IRQCFG + 0x800, 9);
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 1 << 19);
    qtest_writel(q, SPI + 0x60, 0x34); /* reset with next word in flight */
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    assign_bars(q);
    qtest_writel(q, MESSAGE, 0); /* board reset may rewrite its DT in RAM */
    qtest_clock_step(q, 100000);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30), ==, 0);
    qtest_quit(q);
}

/* Phase 10H: barriers are MMIO replies and explicit virtual-clock steps. */
static void setup_msix(QTestState *q, unsigned vector, uint32_t data)
{
    uint64_t table = BAR0 + vector * 16;

    qtest_writel(q, MESSAGE + (vector - 19) * 4, 0);
    qtest_writel(q, table, MESSAGE + (vector - 19) * 4);
    qtest_writel(q, table + 4, 0);
    qtest_writel(q, table + 8, data);
    qtest_writel(q, table + 12, 0);
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
}

static void test_edge_config_no_duplicate(void)
{
    QTestState *q = start();

    setup_spi(q);
    setup_msix(q, 19, 0x12345678);
    qtest_writel(q, IRQCFG, 1); /* edge, no explicit IACK */
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_writel(q, MESSAGE, 0);
    /* Neither unrelated PCI writes nor function unmask create source edges. */
    qtest_writeb(q, ECAM + 0xc, 0x10);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writew(q, ECAM + 0xb2, 0xc000 | 60);
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    /* A real low->high transition still sends a new edge. */
    qtest_readl(q, SPI + 0x60);
    qtest_writel(q, SPI + 0x60, 0x34);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_quit(q);
}

static void test_boundary_refill(void)
{
    QTestState *q = start();

    setup_spi(q);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 7999);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 0);
    qtest_writel(q, SPI + 0x60, 0x34);
    g_assert_cmphex(qtest_readl(q, SPI + 0x20), ==, 1);
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28) & 1, ==, 1);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 2);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x34 ^ 0xa5);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 0);
    qtest_quit(q);
}

static void test_function_pending_ack(void)
{
    QTestState *q = start();

    setup_spi(q);
    setup_msix(q, 19, 0x12345678);
    qtest_writel(q, IRQCFG, 9);
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 7999);
    qtest_writew(q, ECAM + 0xb2, 0xc000 | 60);
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30), ==, 0x10);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 1 << 19);
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 0);
    qtest_readl(q, SPI + 0x60); /* service first event, before RP1 IACK */
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, SPI + 0x60, 0x34);
    qtest_clock_step(q, 8000); /* second event while outstanding */
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 1);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_readl(q, SPI + 0x60);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_quit(q);
}

static void test_delayed_service(void)
{
    QTestState *q = start();

    setup_spi(q);
    setup_msix(q, 19, 0x12345678);
    qtest_writel(q, IRQCFG, 9);
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_writel(q, SPI + 0x60, 0x34);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    qtest_writel(q, MESSAGE, 0);
    /* Software service delay: serializer continues, IRQ stays high. */
    qtest_clock_step(q, 24000);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 2);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28), ==, 0xe);
    qtest_writel(q, IRQCFG + 0x800, 4); /* unserviced level retriggers */
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x34 ^ 0xa5);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    /* Refill after drain creates another CS segment, without losing bytes. */
    qtest_writel(q, SPI + 0x60, 0x56);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x56 ^ 0xa5);
    qtest_quit(q);
}

static void test_disable_abort_boundary(void)
{
    QTestState *q = start();

    setup_spi(q);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_writel(q, SPI + 0x60, 0x34);
    qtest_clock_step(q, 7999);
    qtest_writel(q, SPI + 8, 0);
    qtest_clock_step(q, 16001);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x20), ==, 0);
    g_assert_cmphex(qtest_readl(q, SPI + 0x28), ==, 6);
    setup_spi(q);
    qtest_writel(q, SPI + 0x60, 0x56);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x56 ^ 0xa5);
    qtest_quit(q);
}

static void test_bar_decode_inflight(void)
{
    QTestState *q = start();
    const uint64_t relocated = 0x10800000;

    setup_spi(q);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 7999);
    qtest_writel(q, ECAM + 0x14, relocated);
    g_assert_cmphex(qtest_readl(q, SPI + 0x5c), ==, UINT32_MAX);
    qtest_writel(q, SPI + 8, 0); /* old mapping must not abort the shifter */
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, relocated + 0x50024), ==, 1);
    qtest_writew(q, ECAM + 4, 4); /* BAR memory decode off, BME retained */
    qtest_writel(q, relocated + 0x50008, 0);
    qtest_writew(q, ECAM + 4, 6);
    g_assert_cmphex(qtest_readl(q, relocated + 0x50008), ==, 1);
    g_assert_cmphex(qtest_readl(q, relocated + 0x50060), ==, 0x12 ^ 0xa5);
    qtest_quit(q);
}

static void test_two_pending_vectors(void)
{
    QTestState *q = start();
    uint64_t cfg20 = IRQCFG + 4;

    setup_msix(q, 19, 0x12345678);
    setup_msix(q, 20, 0xabcdef01);
    qtest_writew(q, ECAM + 0xb2, 0xc000 | 60);
    /* Documented TEST command: synthetic events, not a second SPI device. */
    qtest_writel(q, IRQCFG, 3);
    qtest_writel(q, cfg20, 3);
    /* Masked requests coalesce per vector. */
    qtest_writel(q, IRQCFG + 0x800, 2);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, (1 << 19) | (1 << 20));
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE + 4), ==, 0);
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    g_assert_cmphex(qtest_readl(q, MESSAGE + 4), ==, 0xabcdef01);
    qtest_quit(q);
}

static void test_bme_inflight(void)
{
    QTestState *q = start();

    setup_spi(q);
    setup_msix(q, 19, 0x12345678);
    qtest_writel(q, IRQCFG, 9);
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_clock_step(q, 7999);
    qtest_writew(q, ECAM + 4, 2); /* BME off before RX notification */
    qtest_clock_step(q, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x24), ==, 1);
    g_assert_cmphex(qtest_readl(q, SPI + 0x30), ==, 0x10);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 0);
    qtest_writew(q, ECAM + 4, 6);
    /* Outstanding is an attempted notification, not confirmed DMA delivery. */
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writel(q, IRQCFG + 0x800, 4); /* explicit retry of asserted level */
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x12345678);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_quit(q);
}

/* Phase10I: GPIO20 output -> GPIO21 input, explicitly synthetic. */
#define GPIO_IO (BAR1 + 0xd0000)
#define GPIO_RIO (BAR1 + 0xe0000)
#define GPIO_PADS (BAR1 + 0xf0000)
#define GPIO_CFG (BAR1 + 0x108008)
#define GPIO_CTRL(n) (GPIO_IO + (n) * 8 + 4)

static QTestState *gpio_start(void)
{
    QTestState *q = qtest_init("-machine virt,highmem=off -nodefaults "
        "-device rp1-pci,id=rp1,addr=1,gpio-lab=on,native-clock=on "
        "-device ssi-test-slave,bus=spi,cs=0");
    assign_bars(q);
    return q;
}

static void gpio_lines(QTestState *q)
{
    qtest_writel(q, GPIO_PADS + 4 + 20 * 4, 0x52);
    qtest_writel(q, GPIO_PADS + 4 + 21 * 4, 0x52);
    qtest_writel(q, GPIO_CTRL(20), 0x85);
    qtest_writel(q, GPIO_CTRL(21), 0x85);
    qtest_writel(q, GPIO_RIO + 0x2004, 1 << 20);
}

static void gpio_msix(QTestState *q)
{
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, BAR0, MESSAGE);
    qtest_writel(q, BAR0 + 4, 0);
    qtest_writel(q, BAR0 + 8, 0x50505050);
    qtest_writel(q, BAR0 + 12, 0);
    qtest_writew(q, ECAM + 0xb2, 0x8000 | 60);
    qtest_writel(q, GPIO_CFG, 9);
    qtest_writel(q, GPIO_CTRL(21) + 0x2000, 1 << 21);
    qtest_writel(q, GPIO_IO + 0x211c, 1 << 21);
}

static void test_gpio_registers(void)
{
    QTestState *q = gpio_start();

    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(20)), ==, 0x9f);
    g_assert_cmphex(qtest_readl(q, GPIO_PADS + 84), ==, 0x92);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 4), ==, 0);
    gpio_lines(q);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 8), ==, 3 << 20);
    qtest_writel(q, GPIO_RIO + 0x1000, 1 << 20); /* atomic XOR */
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 8), ==, 0);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    qtest_writel(q, GPIO_RIO + 0x3004, 1 << 20); /* direction input */
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 8), ==, 0);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO), ==, 1 << 20);
    /* Unsupported lines, banks and alt functions cannot report success. */
    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(19)), ==, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x4004), ==, UINT32_MAX);
    qtest_writel(q, GPIO_RIO + 0x2004, 1 << 19);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 4), ==, 0);
    qtest_writel(q, GPIO_CTRL(21), 0x80); /* unimplemented ALT0 */
    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(21)), ==, 0x85);
    qtest_writel(q, GPIO_CTRL(21) + 0x2000, 1 << 24); /* filter IRQ */
    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(21)), ==, 0x85);
    qtest_quit(q);
}

static void test_gpio_irq(void)
{
    QTestState *q = gpio_start();

    gpio_lines(q);
    gpio_msix(q);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x124), ==, 1 << 21);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x50505050);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x50505050);
    qtest_writel(q, GPIO_CTRL(21) + 0x2000, 1 << 28);
    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(21)) & (1 << 28), ==, 0);
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x124), ==, 0);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writel(q, BAR0 + 12, 1);
    qtest_writel(q, GPIO_RIO + 0x3000, 1 << 20);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 1);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writel(q, BAR0 + 12, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x50505050);
    /* Mask the peripheral, retain its edge and rearm after unmask. */
    qtest_writel(q, GPIO_IO + 0x311c, 1 << 21);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writel(q, GPIO_IO + 0x211c, 1 << 21);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x50505050);
    /* Level-high cannot be acknowledged away while the input remains high. */
    qtest_writel(q, GPIO_CTRL(21), 0x85 | (1 << 23) | (1 << 28));
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x124), ==, 1 << 21);
    qtest_writel(q, GPIO_CTRL(21) + 0x2000, 1 << 28);
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x124), ==, 1 << 21);
    qtest_writel(q, GPIO_RIO + 0x3000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, GPIO_IO + 0x124), ==, 0);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_quit(q);
}

static void test_gpio_reset_clock(void)
{
    QTestState *q = gpio_start();

    gpio_lines(q);
    gpio_msix(q);
    qtest_writel(q, BAR1 + 0x18014, 0); /* clock-off MMIO is unsupported */
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO), ==, UINT32_MAX);
    qtest_writel(q, BAR1 + 0x18014, 0x802);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO), ==, 0);
    qtest_writel(q, BAR0 + 12, 1);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 1);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    assign_bars(q);
    qtest_writel(q, MESSAGE, 0);
    qtest_clock_step(q, 100000);
    g_assert_cmphex(qtest_readl(q, GPIO_CTRL(21)), ==, 0x9f);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO), ==, 0);
    g_assert_cmphex(qtest_readl(q, GPIO_RIO + 4), ==, 0);
    g_assert_cmphex(qtest_readl(q, BAR0 + 0x1000), ==, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_quit(q);
}

static void test_gpio_spi_bme(void)
{
    QTestState *q = gpio_start();

    gpio_lines(q);
    gpio_msix(q);
    setup_spi(q);
    qtest_writel(q, BAR0 + 19 * 16, MESSAGE + 4);
    qtest_writel(q, BAR0 + 19 * 16 + 8, 0x19191919);
    qtest_writel(q, BAR0 + 19 * 16 + 12, 0);
    qtest_writel(q, MESSAGE + 4, 0);
    qtest_writel(q, IRQCFG, 9);
    qtest_writel(q, SPI + 0x2c, 0x10);
    qtest_writel(q, SPI + 0x60, 0x12);
    qtest_writew(q, ECAM + 4, 2);
    qtest_writel(q, GPIO_RIO + 0x2000, 1 << 20);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    qtest_writew(q, ECAM + 4, 6);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0x50505050);
    g_assert_cmphex(qtest_readl(q, MESSAGE + 4), ==, 0);
    qtest_clock_step(q, 8000);
    g_assert_cmphex(qtest_readl(q, MESSAGE + 4), ==, 0x19191919);
    g_assert_cmphex(qtest_readl(q, SPI + 0x60), ==, 0x12 ^ 0xa5);
    qtest_writel(q, GPIO_CTRL(21) + 0x2000, 1 << 28);
    qtest_writel(q, MESSAGE, 0);
    qtest_writel(q, MESSAGE + 4, 0);
    qtest_writel(q, GPIO_CFG + 0x800, 4);
    qtest_writel(q, IRQCFG + 0x800, 4);
    g_assert_cmphex(qtest_readl(q, MESSAGE), ==, 0);
    g_assert_cmphex(qtest_readl(q, MESSAGE + 4), ==, 0);
    qtest_quit(q);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/rp1/pci-reset-registers", test_pci);
    qtest_add_func("/rp1/bar2-size-access-relocation-reset", test_bar2);
    qtest_add_func("/rp1/spi-transfer-cs", test_transfer);
    qtest_add_func("/rp1/fifo-errors-reset", test_errors_reset);
    qtest_add_func("/rp1/msix-level-ack-mask", test_msix);
    qtest_add_func("/rp1/frame-config-rx-overflow", test_config_overflow);
    qtest_add_func("/rp1/tx-fifo-shifter-irq-lead", test_shift_pipeline);
    qtest_add_func("/rp1/drain-refill-deadline", test_drain_refill);
    qtest_add_func("/rp1/reset-active-pending-msix", test_reset_pending_msix);
    qtest_add_func("/rp1/queued-frame-periods", test_queued_frame_periods);
    qtest_add_func("/rp1/h-edge-config-no-duplicate",
                   test_edge_config_no_duplicate);
    qtest_add_func("/rp1/h-refill-before-completion", test_boundary_refill);
    qtest_add_func("/rp1/h-function-pending-ack", test_function_pending_ack);
    qtest_add_func("/rp1/h-delayed-service", test_delayed_service);
    qtest_add_func("/rp1/h-disable-abort-boundary",
                   test_disable_abort_boundary);
    qtest_add_func("/rp1/h-bar-decode-inflight", test_bar_decode_inflight);
    qtest_add_func("/rp1/h-two-pending-vectors", test_two_pending_vectors);
    qtest_add_func("/rp1/h-bme-inflight", test_bme_inflight);
    qtest_add_func("/rp1/i-gpio-registers-errors", test_gpio_registers);
    qtest_add_func("/rp1/i-gpio-msix-edge-level-mask", test_gpio_irq);
    qtest_add_func("/rp1/i-gpio-reset-clock", test_gpio_reset_clock);
    qtest_add_func("/rp1/i-gpio-spi-isolation-bme", test_gpio_spi_bme);
    return g_test_run();
}

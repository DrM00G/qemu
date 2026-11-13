/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local experiment, not for upstream submission. */
#include "qemu/osdep.h"
#include "hw/arm/cm5io-dev.h"
#include "libqtest.h"

static char *image;
static char *overlay;
static uint8_t pattern[1024];

static QTestState *start(void)
{
    return qtest_initf("-M cm5io-dev,native-emmc=on,native-mip=on "
        "-m 512M -nodefaults -drive file=%s,if=none,format=qcow2,id=card "
        "-device emmc,drive=card,boot-partition-size=0,"
        "rpmb-partition-size=0", overlay);
}

static uint32_t cmd(QTestState *q, unsigned op, uint32_t arg, unsigned flags)
{
    qtest_writel(q, CM5_EMMC_HOST + 0x30, UINT32_MAX);
    qtest_writel(q, CM5_EMMC_HOST + 8, arg);
    qtest_writew(q, CM5_EMMC_HOST + 0xe, (op << 8) | flags);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x30) & 1, ==, 1);
    return qtest_readl(q, CM5_EMMC_HOST + 0x10);
}

static void init_card(QTestState *q)
{
    qtest_writeb(q, CM5_EMMC_HOST + 0x2f, 1);
    qtest_writew(q, CM5_EMMC_HOST + 0x2c, 7);
    qtest_writeb(q, CM5_EMMC_HOST + 0x29, 0xf);
    qtest_writel(q, CM5_EMMC_HOST + 0x34, UINT32_MAX);
    qtest_writel(q, CM5_EMMC_HOST + 0x38, UINT32_MAX);
    cmd(q, 0, 0, 0);
    g_assert_cmphex(cmd(q, 1, 0x40ff8000, 2) & 0xc0000000, ==, 0xc0000000);
    cmd(q, 2, 0, 1);
    cmd(q, 3, 1 << 16, 2);
    cmd(q, 9, 1 << 16, 1);
    cmd(q, 7, 1 << 16, 3);
}

static void test_config_reset(void)
{
    QTestState *q = start();

    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0xfe) & 0xff, ==, 2);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_HOST + 0x40), ==, 0x0104c881);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x1ac), ==, 1);
    qtest_writel(q, CM5_EMMC_CFG, UINT32_MAX);
    qtest_writel(q, CM5_EMMC_CFG + 0x44, UINT32_MAX);
    qtest_writel(q, CM5_EMMC_CFG + 0x4c, 0x30c8);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG), ==, 0xc0000000);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x44), ==, 3);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x4c), ==, 0x30c8);
    qtest_writel(q, CM5_EMMC_CFG + 0x100, UINT32_MAX);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x100), ==, 0);
    init_card(q);
    qtest_qmp_assert_success(q, "{ 'execute': 'system_reset' }");
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x44), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_CFG + 0x4c), ==, 0);
    g_assert_cmphex(qtest_readl(q, CM5_EMMC_HOST + 0x34), ==, 0);
    init_card(q);
    qtest_quit(q);
}

static void read_data(QTestState *q, uint8_t *data, unsigned bytes)
{
    unsigned i;

    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x30) & 0x20, ==, 0x20);
    for (i = 0; i < bytes; i += 4) {
        uint32_t v = qtest_readl(q, CM5_EMMC_HOST + 0x20);
        data[i] = v;
        data[i + 1] = v >> 8;
        data[i + 2] = v >> 16;
        data[i + 3] = v >> 24;
    }
}

static void test_pio_read_irq(void)
{
    QTestState *q = start();
    uint8_t data[1024];
    unsigned irq = CM5_EMMC_IRQ + 32;
    uint64_t pending = CM5_GIC_DIST + 0x200 + irq / 32 * 4;
    uint32_t bit = 1U << (irq % 32);

    init_card(q);
    /* Real EXT_CSD through command/data path, absent boot/RPMB, capacity. */
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (1 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x10);
    cmd(q, 8, 0, 0x22);
    read_data(q, data, 512);
    g_assert_cmpuint(data[226], ==, 0);
    g_assert_cmpuint(data[168], ==, 0);
    g_assert_cmphex(data[215], ==, 0);
    g_assert_cmphex(data[214], ==, 0x80); /* 4GiB / 512 */
    /* Single-block PIO read; the level IRQ reaches physical GIC SPI273. */
    qtest_writeb(q, CM5_GIC_DIST + 0x800 + irq, 1);
    cmd(q, 17, 0, 0x22);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, bit);
    read_data(q, data, 512);
    g_assert_cmpmem(data, 512, pattern, 512);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x30) & 2, ==, 2);
    qtest_writel(q, CM5_EMMC_HOST + 0x30, UINT32_MAX);
    qtest_writel(q, pending + 0x80, bit);
    g_assert_cmphex(qtest_readl(q, pending) & bit, ==, 0);
    /* DMA requests are suppressed by this PIO-only capability profile. */
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x37);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0xc) & 1, ==, 0);
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (2 << 16));
    cmd(q, 18, 0, 0x22);
    read_data(q, data, 1024);
    g_assert_cmpmem(data, 1024, pattern, 1024);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x30) & 2, ==, 2);
    /* Linux v3 PIO uses Auto CMD23 rather than an explicit stop. */
    qtest_writel(q, CM5_EMMC_HOST, 2); /* Argument2 */
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (2 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x3a);
    cmd(q, 18, 0, 0x22);
    read_data(q, data, 1024);
    g_assert_cmpmem(data, 1024, pattern, 1024);
    g_assert_cmphex(cmd(q, 13, 1 << 16, 2) & 0x1e00, ==, 4 << 9);
    /* Auto CMD23 in standby must fail before the main data command. */
    cmd(q, 7, 0, 0);
    qtest_writel(q, CM5_EMMC_HOST + 0x30, UINT32_MAX);
    qtest_writel(q, CM5_EMMC_HOST, 2);
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (2 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x3a);
    qtest_writew(q, CM5_EMMC_HOST + 0xe, (18 << 8) | 0x22);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x32) & 0x100,
                    ==, 0x100);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x3c), ==, 2);
    qtest_quit(q);
}

static void test_errors_immutable(void)
{
    QTestState *q = start();
    uint8_t data[1024];
    int fd;
    uint32_t status;

    init_card(q);
    /* Unsupported command times out and its error status is W1C. */
    cmd(q, 63, 0, 2);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x32) & 1, ==, 1);
    qtest_writel(q, CM5_EMMC_HOST + 0x30, UINT32_MAX);
    g_assert_cmphex(qtest_readw(q, CM5_EMMC_HOST + 0x32), ==, 0);
    status = cmd(q, 17, 0xffffffff, 2);
    g_assert_cmphex(status & (1U << 30), !=, 0); /* ADDRESS_ERROR */
    cmd(q, 13, 1 << 16, 2);
    /* A real card write changes the disposable overlay, never the backing. */
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (1 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0);
    cmd(q, 24, 0, 0x22);
    for (fd = 0; fd < 128; fd++) {
        qtest_writel(q, CM5_EMMC_HOST + 0x20, 0x12345678);
    }
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x10);
    cmd(q, 17, 0, 0x22);
    read_data(q, data, 512);
    g_assert_cmphex(data[0], ==, 0x78);
    g_assert_cmphex(data[511], ==, 0x12);
    qtest_writel(q, CM5_EMMC_HOST, 2);
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (2 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x2a);
    cmd(q, 25, 0, 0x22);
    for (fd = 0; fd < 256; fd++) {
        qtest_writel(q, CM5_EMMC_HOST + 0x20, 0x87654321);
    }
    g_assert_cmphex(cmd(q, 13, 1 << 16, 2) & 0x1e00, ==, 4 << 9);
    qtest_quit(q);
    fd = open(image, O_RDONLY);
    g_assert_cmpint(fd, >=, 0);
    g_assert_cmpint(read(fd, data, sizeof(data)), ==, sizeof(data));
    g_assert_cmpmem(data, sizeof(data), pattern, sizeof(pattern));
    close(fd);
}

static void test_erase_range(void)
{
    QTestState *q = start();
    uint8_t data[512];
    int64_t started;
    unsigned i;

    init_card(q);
    cmd(q, 35, 2048, 2);
    cmd(q, 36, 2048 + 262144 - 1, 2);
    started = g_get_monotonic_time();
    cmd(q, 38, 0, 3);
    g_test_message("ERASE_128M_US=%" PRId64,
                   g_get_monotonic_time() - started);
    qtest_writel(q, CM5_EMMC_HOST + 4, 512 | (1 << 16));
    qtest_writew(q, CM5_EMMC_HOST + 0xc, 0x10);
    cmd(q, 17, 2048, 0x22);
    read_data(q, data, sizeof(data));
    for (i = 0; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0xff);
    }
    cmd(q, 17, 2048 + 262144 - 1, 0x22);
    read_data(q, data, sizeof(data));
    for (i = 0; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0xff);
    }
    cmd(q, 17, 2047, 0x22);
    read_data(q, data, sizeof(data));
    for (i = 0; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0);
    }
    cmd(q, 17, 2048 + 262144, 0x22);
    read_data(q, data, sizeof(data));
    for (i = 0; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0);
    }
    /* Out-of-range must not extend the backing image at exactly its size. */
    cmd(q, 35, 4U * 1024 * 1024 * 2, 2);
    cmd(q, 36, 4U * 1024 * 1024 * 2, 2);
    g_assert_cmphex(cmd(q, 38, 0, 3) & (1U << 31), !=, 0);
    cmd(q, 13, 1 << 16, 2);
    /* A partial final batch must keep the inclusive sector boundary. */
    cmd(q, 35, 2049, 2);
    cmd(q, 36, 2051, 2);
    cmd(q, 38, 0, 3);
    g_assert_cmphex(cmd(q, 13, 1 << 16, 2) & 0x1e00, ==, 4 << 9);
    qtest_quit(q);
}

int main(int argc, char **argv)
{
    const char *dir = g_getenv("CM5_PHASE8_IMAGE_DIR");
    int fd;
    unsigned i;
    int result;
    g_autofree char *imgtool = NULL;
    g_autofree char *bindir = NULL;
    const char *args[10];

    g_test_init(&argc, &argv, NULL);
    g_assert_nonnull(dir);
    image = g_strdup_printf("%s/qtest-emmc-XXXXXX", dir);
    fd = g_mkstemp(image);
    g_assert_cmpint(fd, >=, 0);
    g_assert_cmpint(ftruncate(fd, 4ULL << 30), ==, 0);
    for (i = 0; i < sizeof(pattern); i++) {
        pattern[i] = i ^ (i >> 8) ^ 0xa5;
    }
    g_assert_cmpint(write(fd, pattern, sizeof(pattern)), ==, sizeof(pattern));
    close(fd);
    overlay = g_strconcat(image, ".qcow2", NULL);
    bindir = g_path_get_dirname(qtest_qemu_binary(NULL));
    imgtool = g_build_filename(bindir, "qemu-img", NULL);
    args[0] = imgtool;
    args[1] = "create";
    args[2] = "-f";
    args[3] = "qcow2";
    args[4] = "-F";
    args[5] = "raw";
    args[6] = "-b";
    args[7] = image;
    args[8] = overlay;
    args[9] = NULL;
    g_assert_true(g_spawn_sync(NULL, (char **)args, NULL, 0, NULL, NULL,
                              NULL, NULL, &result, NULL));
    g_assert_cmpint(result, ==, 0);
    qtest_add_func("/bcm2712-sdhci/config-system-reset", test_config_reset);
    qtest_add_func("/bcm2712-sdhci/emmc-pio-read-irq", test_pio_read_irq);
    qtest_add_func("/bcm2712-sdhci/errors-readonly", test_errors_immutable);
    qtest_add_func("/bcm2712-sdhci/erase-range", test_erase_range);
    result = g_test_run();
    unlink(overlay);
    g_free(overlay);
    unlink(image);
    g_free(image);
    return result;
}

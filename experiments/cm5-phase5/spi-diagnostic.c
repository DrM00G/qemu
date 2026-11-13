/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Local hardware experiment. Uses the real Linux spidev ioctl interface. */
#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    uint8_t tx[257], rx[257];
    const unsigned lengths[] = { 1, 4, 63, 64, 65, 257 };
    const unsigned speeds[] = { 100000, 1000000, 5000000 };
    int fd, failures = 0;
    unsigned mode, l, f, i;

    if (argc != 2 || (fd = open(argv[1], O_RDWR)) < 0) {
        perror("open spidev");
        return 1;
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    for (mode = 0; mode < 4; mode++) {
        uint8_t m = mode;
        if (ioctl(fd, SPI_IOC_WR_MODE, &m) < 0) {
            perror("set mode");
            return 1;
        }
        for (f = 0; f < sizeof(speeds) / sizeof(speeds[0]); f++) {
            for (l = 0; l < sizeof(lengths) / sizeof(lengths[0]); l++) {
                unsigned len = lengths[l];
                struct spi_ioc_transfer tr = {
                    .tx_buf = (uintptr_t)tx, .rx_buf = (uintptr_t)rx,
                    .len = len, .speed_hz = speeds[f], .bits_per_word = 8,
                };
                int ret;
                for (i = 0; i < len; i++) {
                    tx[i] = (i + 1) * 0x10;
                }
                memset(rx, 0, sizeof(rx));
                printf("SPI_IOC_MESSAGE(1) mode=%u hz=%u len=%u TX=",
                       mode, speeds[f], len);
                for (i = 0; i < len; i++) {
                    printf("%02x", tx[i]);
                }
                printf("\n");
                ret = ioctl(fd, SPI_IOC_MESSAGE(1), &tr);
                printf("SPI_RESULT ret=%d errno=%d RX=", ret,
                       ret < 0 ? errno : 0);
                for (i = 0; i < len; i++) {
                    printf("%02x", rx[i]);
                    if (rx[i] != (uint8_t)(tx[i] ^ 0xa5)) {
                        failures++;
                    }
                }
                printf("\n");
                failures += ret != (int)len;
            }
        }
    }
    /* Linux must reject a non-supported frame size. */
    {
        struct spi_ioc_transfer bad = {
            .tx_buf = (uintptr_t)tx, .rx_buf = (uintptr_t)rx,
            .len = 1, .bits_per_word = 3, .speed_hz = 1000000,
        };
        int ret = ioctl(fd, SPI_IOC_MESSAGE(1), &bad);
        printf("SPI_INVALID_BPW ret=%d errno=%d\n", ret, errno);
        failures += ret != -1 || errno != EINVAL;
    }
    close(fd);
    printf("SPI_DIAGNOSTIC=%s failures=%d\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}

#ifndef PHASE3_INTERFACES_H
#define PHASE3_INTERFACES_H
#include <errno.h>
#include <stddef.h>
/* Future laboratory adapters. These boundaries provide no emulated hardware. */
static inline int flight_spi_transfer(const void *tx, void *rx, size_t bytes)
{
    (void)tx; (void)rx; (void)bytes;
    return -ENOSYS;
}
static inline int flight_uart_send(const void *data, size_t bytes)
{
    (void)data; (void)bytes;
    return -ENOSYS;
}
#endif

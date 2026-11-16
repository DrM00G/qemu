/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * DW_apb_ssi v4.02a, single-lane PIO subset for local RP1 research.
 * Register contract: Linux drivers/spi/spi-dw{.h,-core.c} and DW_apb_ssi
 * databook v4.02a. Synthesis-dependent defaults are experimental choices.
 * AI-assisted implementation; not intended for upstream submission.
 */
#include "qemu/osdep.h"
#include "hw/ssi/dw-apb-ssi.h"
#include "hw/core/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "trace.h"

#define CTRLR0  0x00
#define CTRLR1  0x04
#define SSIENR  0x08
#define SER     0x10
#define BAUDR   0x14
#define TXFTLR  0x18
#define RXFTLR  0x1c
#define TXFLR   0x20
#define RXFLR   0x24
#define SR      0x28
#define IMR     0x2c
#define ISR     0x30
#define RISR    0x34
#define TXOICR  0x38
#define RXOICR  0x3c
#define RXUICR  0x40
#define MSTICR  0x44
#define ICR     0x48
#define IDR     0x58
#define VERSION 0x5c
#define DR      0x60
#define R(s, r) ((s)->regs[(r) / 4])

static uint32_t dw_ssi_raw(DWAPBSSIState *s)
{
    return s->errors | (R(s, SSIENR) && s->tx_count <= R(s, TXFTLR)) |
           ((s->rx_count > R(s, RXFTLR)) ? BIT(4) : 0);
}

static void dw_ssi_diag(DWAPBSSIState *s, const char *event)
{
    /* Nonarchitectural, bounded first-event capture; never affects pacing. */
    if (s->diagnostic_left) {
        s->diagnostic_left--;
        trace_dw_apb_ssi_state(event, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
            s->tx_count, s->rx_count, s->shift_busy, s->active_cs,
            dw_ssi_raw(s), R(s, IMR), timer_pending(s->timer) ?
            timer_expire_time_ns(s->timer) : -1);
    }
}

/* Targeted metadata, independent of the old first-256-event window. */
static void dw_ssi_boundary(DWAPBSSIState *s, const char *event)
{
    uint32_t state = R(s, SER) | (R(s, SSIENR) << 4) |
                     (s->shift_busy << 5) | (s->irq_level << 6) |
                     (R(s, TXFTLR) << 8) | (R(s, RXFTLR) << 16);

    if (!trace_event_get_state_backends(TRACE_DW_APB_SSI_BOUNDARY) ||
        !s->boundary_left) {
        return;
    }
    s->boundary_left--;
    trace_dw_apb_ssi_boundary(event, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
        s->diagnostic_epoch, s->completed_words, s->diagnostic_segment,
        s->tx_count, s->rx_count, dw_ssi_raw(s), R(s, IMR), state);
    trace_dw_apb_ssi_timer(event, s->diagnostic_epoch, s->completed_words,
        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL), s->armed_at,
        s->last_deadline, s->last_callback, R(s, BAUDR), s->input_hz);
    if (!s->boundary_left) {
        trace_dw_apb_ssi_boundary("CAPTURE_EXHAUSTED", 0, 0, 0, 0,
                                 0, 0, 0, 0, 0);
    }
}

static void dw_ssi_irq(DWAPBSSIState *s)
{
    uint32_t raw = dw_ssi_raw(s);
    bool level = !!(raw & R(s, IMR));

    if (raw != s->diagnostic_raw) {
        s->diagnostic_raw = raw;
        dw_ssi_boundary(s, "threshold");
    }

    if (level != s->irq_level) {
        s->irq_level = level;
        dw_ssi_diag(s, "irq");
        dw_ssi_boundary(s, "irq-level");
    }
    qemu_set_irq(s->irq, level);
}

static void dw_ssi_cs(DWAPBSSIState *s, uint32_t selected)
{
    unsigned i;

    if (selected == s->active_cs) {
        return;
    }
    if (selected) {
        s->diagnostic_segment++;
    }
    trace_dw_apb_ssi_cs(selected);
    s->active_cs = selected;
    dw_ssi_diag(s, "cs");
    dw_ssi_boundary(s, selected ? "cs-assert" : "cs-deassert");
    for (i = 0; i < 4; i++) {
        DeviceState *dev = ssi_get_cs(s->bus, i);
        if (dev) {
            SSIPeripheralClass *sc = SSI_PERIPHERAL_GET_CLASS(dev);
            if (sc->cs_polarity == SSI_CS_NONE || sc->transfer == NULL) {
                continue;
            }
            qemu_set_irq(qdev_get_gpio_in_named(dev, SSI_GPIO_CS, 0),
                         sc->cs_polarity == SSI_CS_LOW ?
                         !(selected & BIT(i)) : !!(selected & BIT(i)));
        }
    }
}

static bool dw_ssi_supported(DWAPBSSIState *s)
{
    uint32_t c = R(s, CTRLR0);
    unsigned bits = ((c >> 16) & 31) + 1;

    /* Motorola SPI, full duplex / transmit only, 4..32 bit data frames. */
    return !(c & (3 << 4)) && !(c & (3 << 21)) &&
           ((c >> 8) & 3) <= 1 && bits >= 4;
}

static void dw_ssi_schedule(DWAPBSSIState *s)
{
    if (!R(s, SSIENR) || !R(s, SER) || R(s, BAUDR) < 2 ||
        !dw_ssi_supported(s) ||
        (s->shift_busy && s->active_cs != R(s, SER))) {
        timer_del(s->timer);
        s->shift_busy = false;
        s->remaining_clock_work = 0;
        dw_ssi_cs(s, 0);
    } else if (!s->input_hz) {
        /* Logical clock pause; do not manufacture a completed frame. */
        timer_del(s->timer);
    } else {
        if (!s->shift_busy && s->tx_count) {
            s->shift_tx = s->tx[s->tx_head];
            s->shift_bits = ((R(s, CTRLR0) >> 16) & 31) + 1;
            s->tx_head = (s->tx_head + 1) % DW_SSI_FIFO_DEPTH;
            s->tx_count--;
            s->shift_busy = true;
            s->remaining_clock_work = (uint64_t)s->shift_bits *
                                      R(s, BAUDR) * 1000000000;
            dw_ssi_cs(s, R(s, SER));
            dw_ssi_diag(s, "shift-load");
        }
        if (s->shift_busy && !timer_pending(s->timer)) {
            int64_t ns = MAX(1, s->remaining_clock_work / s->input_hz +
                                !!(s->remaining_clock_work % s->input_hz));
            s->armed_at = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            s->progress_at = s->armed_at;
            s->last_deadline = s->armed_at + ns;
            timer_mod(s->timer, s->last_deadline);
            if (s->completed_words <= 2 || s->tx_count <= 1) {
                dw_ssi_boundary(s, "arm");
            }
        } else if (!s->shift_busy) {
            dw_ssi_cs(s, 0);
        }
    }
    dw_ssi_irq(s);
}

void dw_apb_ssi_set_frequency(DWAPBSSIState *s, uint64_t hz)
{
    int64_t now;

    if (hz == s->input_hz) {
        return;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (s->shift_busy && s->input_hz) {
        uint64_t elapsed = MAX(0, now - s->progress_at);
        uint64_t needed = s->remaining_clock_work / s->input_hz +
                          !!(s->remaining_clock_work % s->input_hz);

        /*
         * Preserve consumed input clocks across a gate/divider change.
         * Saturating before multiplication also bounds the product.
         * This is aggregate serializer progress, not electrical bit phase.
         */
        s->remaining_clock_work = elapsed >= needed ? 0 :
            s->remaining_clock_work - elapsed * s->input_hz;
    }
    s->input_hz = hz;
    timer_del(s->timer);
    dw_ssi_boundary(s, "input-clock-change");
    dw_ssi_schedule(s);
}

static void dw_ssi_tick(void *opaque)
{
    DWAPBSSIState *s = opaque;
    unsigned bits = s->shift_bits;
    uint32_t mask = bits == 32 ? UINT32_MAX : (1U << bits) - 1;
    uint32_t tx = s->shift_tx & mask;
    uint32_t rx;

    if (!s->shift_busy) {
        return;
    }
    s->last_callback = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (s->tx_count <= 1) {
        dw_ssi_boundary(s, "complete-before");
    }
    s->shift_busy = false;
    s->remaining_clock_work = 0;
    rx = (R(s, CTRLR0) & BIT(11)) ? tx : ssi_transfer(s->bus, tx);
    rx &= mask;
    trace_dw_apb_ssi_transfer(s->active_cs, bits, tx, rx);
    if (!((R(s, CTRLR0) >> 8) & 3)) {
        if (s->rx_count == DW_SSI_FIFO_DEPTH) {
            s->errors |= BIT(3);
        } else {
            s->rx[(s->rx_head + s->rx_count) % DW_SSI_FIFO_DEPTH] = rx;
            s->rx_count++;
        }
    }
    s->completed_words++;
    if (s->tx_count <= 1) {
        dw_ssi_boundary(s, "complete-after");
    }
    dw_ssi_diag(s, "shift-done");
    dw_ssi_schedule(s);
}

static uint64_t dw_ssi_read(void *opaque, hwaddr addr, unsigned size)
{
    DWAPBSSIState *s = opaque;
    uint32_t val = 0;

    if (addr >= DR && addr <= 0xec) {
        if (s->rx_count) {
            val = s->rx[s->rx_head];
            s->rx_head = (s->rx_head + 1) % DW_SSI_FIFO_DEPTH;
            s->rx_count--;
        } else {
            s->errors |= BIT(2);
        }
    } else {
        switch (addr) {
        case TXFLR:
            val = s->tx_count;
            break;
        case RXFLR:
            val = s->rx_count;
            break;
        case SR:
            val = (s->shift_busy ? BIT(0) : 0) |
                  (s->tx_count < DW_SSI_FIFO_DEPTH ? BIT(1) : 0) |
                  (!s->tx_count ? BIT(2) : 0) |
                  (s->rx_count ? BIT(3) : 0) |
                  (s->rx_count == DW_SSI_FIFO_DEPTH ? BIT(4) : 0);
            break;
        case ISR:
            val = dw_ssi_raw(s) & R(s, IMR);
            break;
        case RISR:
            val = dw_ssi_raw(s);
            break;
        case TXOICR:
        case RXOICR:
        case RXUICR:
        case MSTICR: {
            unsigned bit = addr == TXOICR ? 1 : addr == RXOICR ? 3 :
                           addr == RXUICR ? 2 : 5;
            val = !!(s->errors & BIT(bit));
            s->errors &= ~BIT(bit);
            break;
        }
        case ICR:
            val = !!s->errors;
            s->errors = 0;
            break;
        case VERSION:
            val = 0x3430322a; /* 4.02a, RP1 datasheet section 3.6 */
            break;
        case IDR:
            val = 0; /* synthesis-dependent ID, experimental default */
            break;
        default:
            if (addr < sizeof(s->regs)) {
                val = s->regs[addr / 4];
            }
            break;
        }
    }
    dw_ssi_irq(s);
    return val;
}

static void dw_ssi_write(void *opaque, hwaddr addr, uint64_t val,
                         unsigned size)
{
    DWAPBSSIState *s = opaque;

    if (addr >= DR && addr <= 0xec) {
        if (!R(s, SSIENR)) {
            return;
        }
        if (s->tx_count == DW_SSI_FIFO_DEPTH) {
            s->errors |= BIT(1);
        } else {
            if (!s->tx_count) {
                dw_ssi_boundary(s, s->shift_busy ?
                                "refill-shifting" : "refill-idle");
            }
            s->tx[(s->tx_head + s->tx_count) % DW_SSI_FIFO_DEPTH] = val;
            s->tx_count++;
            dw_ssi_diag(s, "tx-write");
        }
    } else {
        switch (addr) {
        case CTRLR0:
            if (!R(s, SSIENR)) {
                /* DFS[3:0] reads zero on a 32-bit synthesis. */
                R(s, CTRLR0) = val & 0x00ffffff & ~0xf;
                if (!dw_ssi_supported(s)) {
                    qemu_log_mask(LOG_UNIMP,
                                  "dw-apb-ssi: unsupported CTRLR0 0x%x\n",
                                  R(s, CTRLR0));
                }
            }
            break;
        case CTRLR1:
            if (!R(s, SSIENR)) {
                R(s, CTRLR1) = val & 0xffff;
            }
            break;
        case SSIENR:
            if ((val & 1) && !R(s, SSIENR)) {
                s->diagnostic_epoch++;
                s->completed_words = 0;
            }
            R(s, SSIENR) = val & 1;
            if (!(val & 1)) {
                s->tx_head = s->rx_head = s->tx_count = s->rx_count = 0;
                s->errors = 0;
            }
            break;
        case SER:
            R(s, SER) = val & 0xf;
            break;
        case BAUDR:
            if (!R(s, SSIENR)) {
                R(s, BAUDR) = val & 0xfffe;
            }
            break;
        case TXFTLR:
        case RXFTLR:
            s->regs[addr / 4] = val & (DW_SSI_FIFO_DEPTH - 1);
            break;
        case IMR:
            R(s, IMR) = val & 0x3f;
            break;
        case 0xf0: /* RX_SAMPLE_DLY */
            if (!R(s, SSIENR)) {
                s->regs[addr / 4] = val & 0xff;
            }
            break;
        default:
            qemu_log_mask(LOG_UNIMP,
                          "dw-apb-ssi: unimplemented write @0x%" HWADDR_PRIx
                          " = 0x%" PRIx64 "\n", addr, val);
            break;
        }
    }
    if (addr == SSIENR || addr == SER || addr == IMR) {
        dw_ssi_boundary(s, addr == SSIENR ? "enable-write" :
                        addr == SER ? "ser-write" : "mask-write");
    }
    dw_ssi_schedule(s);
}

static const MemoryRegionOps dw_ssi_ops = {
    .read = dw_ssi_read,
    .write = dw_ssi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void dw_ssi_reset(DeviceState *dev)
{
    DWAPBSSIState *s = DW_APB_SSI(dev);

    timer_del(s->timer);
    s->shift_busy = false;
    s->shift_tx = s->shift_bits = 0;
    s->remaining_clock_work = 0;
    s->progress_at = 0;
    s->diagnostic_left = 256;
    s->boundary_left = 65536;
    s->diagnostic_raw = 0;
    s->diagnostic_epoch = s->completed_words = s->diagnostic_segment = 0;
    s->armed_at = s->last_deadline = s->last_callback = -1;
    memset(s->regs, 0, sizeof(s->regs));
    R(s, CTRLR0) = 7 << 16; /* experimental reset frame size: eight bits */
    R(s, IMR) = 0x3f;
    s->tx_head = s->rx_head = s->tx_count = s->rx_count = 0;
    s->errors = 0;
    /* Force inactive levels also on newly attached SSI peripherals. */
    s->active_cs = UINT32_MAX;
    dw_ssi_cs(s, 0);
    dw_ssi_irq(s);
}

static void dw_ssi_init(Object *obj)
{
    DWAPBSSIState *s = DW_APB_SSI(obj);

    memory_region_init_io(&s->mmio, obj, &dw_ssi_ops, s,
                          "dw-apb-ssi", 0x1000);
    qdev_init_gpio_out(DEVICE(obj), &s->irq, 1);
    s->timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, dw_ssi_tick, s);
    s->input_hz = 200000000; /* preserved fallback default */
}

static void dw_ssi_finalize(Object *obj)
{
    timer_free(DW_APB_SSI(obj)->timer);
}

static const VMStateDescription dw_ssi_vmstate = {
    .name = TYPE_DW_APB_SSI,
    .unmigratable = 1,
};

static void dw_ssi_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, dw_ssi_reset);
    dc->vmsd = &dw_ssi_vmstate;
    dc->user_creatable = false;
}

static const TypeInfo dw_ssi_type = {
    .name = TYPE_DW_APB_SSI,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(DWAPBSSIState),
    .instance_init = dw_ssi_init,
    .instance_finalize = dw_ssi_finalize,
    .class_init = dw_ssi_class_init,
};

static void dw_ssi_register_types(void)
{
    type_register_static(&dw_ssi_type);
}
type_init(dw_ssi_register_types)

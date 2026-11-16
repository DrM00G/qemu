/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Local, AI-assisted RP1 GPIO20/21 vertical slice, not for upstream submission.
 * Contract: RP1 Peripherals sections 2.4, 3.1, 3.3 and pinned Linux
 * cff533aec2fa601846766b32ff57204e0a61bed7 drivers/pinctrl/pinctrl-rp1.c.
 * Only SYS_RIO function5 and NULL31; no debounce/filter or electrical timing.
 * Synthetic directional loopback GPIO20 -> GPIO21, absent on physical hardware.
 */
#include "qemu/osdep.h"
#include "hw/gpio/rp1-gpio.h"
#include "hw/core/irq.h"
#include "migration/vmstate.h"
#include "qemu/module.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "trace.h"

#define LINES (BIT(20) | BIT(21))

static bool override(bool value, unsigned setting)
{
    return setting < 2 ? value ^ setting : setting == 3;
}

static bool gpio_out(RP1GPIOState *s, unsigned i)
{
    bool value = (s->ctrl[i] & 31) == 5 && (s->out & BIT(20 + i));
    return override(value, (s->ctrl[i] >> 12) & 3);
}

static bool gpio_oe(RP1GPIOState *s, unsigned i)
{
    bool value = (s->ctrl[i] & 31) == 5 && (s->oe & BIT(20 + i));
    return override(value, (s->ctrl[i] >> 14) & 3) && !(s->pads[i] & BIT(7));
}

static uint32_t gpio_events(RP1GPIOState *s, unsigned i)
{
    return s->edges[i] | (s->sample[i] ? BIT(3) : BIT(2));
}

static bool gpio_pending(RP1GPIOState *s, unsigned i)
{
    bool combined = !!(gpio_events(s, i) & (s->ctrl[i] >> 20));
    return override(combined, s->ctrl[i] >> 30);
}

static uint32_t gpio_intr(RP1GPIOState *s)
{
    return (gpio_pending(s, 0) ? BIT(20) : 0) |
           (gpio_pending(s, 1) ? BIT(21) : 0);
}

static void gpio_update(RP1GPIOState *s)
{
    unsigned i;
    bool irq;

    s->input = 0;
    for (i = 0; i < 2; i++) {
        bool physical = gpio_oe(s, i) ? gpio_out(s, i) :
                        i == 1 && gpio_oe(s, 0) ? gpio_out(s, 0) :
                        !!(s->pads[i] & BIT(3));
        bool sample = physical && (s->pads[i] & BIT(6));
        if (sample != s->sample[i]) {
            s->edges[i] |= sample ? BIT(1) : BIT(0);
        }
        s->sample[i] = sample;
        if ((s->ctrl[i] & 31) == 5 &&
            override(sample, (s->ctrl[i] >> 16) & 3)) {
            s->input |= BIT(20 + i);
        }
    }
    irq = !!((gpio_intr(s) & s->inte) | s->intf);
    if (irq != s->irq_level) {
        s->irq_level = irq;
        trace_rp1_gpio_irq(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                          s->input, gpio_intr(s), s->inte, s->intf, irq);
    }
    /* Input/edge/mask state is visible before notifying RP1 MSI-X. */
    qemu_set_irq(s->irq, irq);
}

void rp1_gpio_set_clock(RP1GPIOState *s, bool running)
{
    /* Clock-off APB access returns an explicit unsupported error. */
    s->clock_running = running;
}

static uint32_t atomic_value(uint32_t old, uint32_t value, unsigned alias)
{
    switch (alias) {
    case 1: return old ^ value;
    case 2: return old | value;
    case 3: return old & ~value;
    default: return value;
    }
}

static bool gpio_access(RP1GPIOWindow *w, hwaddr addr, uint32_t *value,
                        bool write)
{
    RP1GPIOState *s = w->owner;
    unsigned alias = addr >> 12;
    unsigned reg = addr & 0xfff;
    uint32_t *target = NULL, next;
    int i = -1;

    if (!s->clock_running || addr >= 0x4000) {
        return false; /* Banks1/2 are explicitly unsupported. */
    }
    if (w->kind == 0) {
        if (reg == 0x100 || reg == 0x124) {
            if (write) {
                return false;
            }
            *value = reg == 0x100 ? gpio_intr(s) :
                     (gpio_intr(s) & s->inte) | s->intf;
            return true;
        } else if (reg == 0x11c || reg == 0x120) {
            target = reg == 0x11c ? &s->inte : &s->intf;
        } else if (reg >= 20 * 8 && reg <= 21 * 8 + 4) {
            i = reg / 8 - 20;
            if (!(reg & 4)) {
                if (write) {
                    return false;
                }
                *value = (gpio_events(s, i) << 20) |
                         (gpio_pending(s, i) ? BIT(29) : 0) |
                         ((gpio_events(s, i) & (s->ctrl[i] >> 20)) ?
                          BIT(28) : 0) |
                         (s->sample[i] ? BIT(17) : 0) |
                         ((s->input & BIT(20 + i)) ? BIT(19) : 0) |
                         (gpio_oe(s, i) ? BIT(13) : 0) |
                         (((s->ctrl[i] & 31) == 5 &&
                           (s->oe & BIT(20 + i))) ? BIT(12) : 0) |
                         (gpio_out(s, i) ? BIT(9) : 0) |
                         (((s->ctrl[i] & 31) == 5 &&
                           (s->out & BIT(20 + i))) ? BIT(8) : 0);
                return true;
            }
            target = &s->ctrl[i];
        }
    } else if (w->kind == 1) {
        if (reg == 0 || reg == 4) {
            target = reg == 0 ? &s->out : &s->oe;
        } else if ((reg == 8 || reg == 12) && !write) {
            *value = s->input; /* Zero-delay logical synchronizer convention. */
            return true;
        }
    } else {
        if (reg == 0) {
            /* Register metadata, no voltage simulation. */
            target = &s->voltage;
        } else if (reg == 4 + 20 * 4 || reg == 4 + 21 * 4) {
            target = &s->pads[(reg - 4) / 4 - 20];
        }
    }
    if (!target) {
        return false;
    }
    if (!write) {
        *value = *target;
        return true;
    }
    next = atomic_value(*target, *value, alias);
    if (w->kind == 0 && i >= 0) {
        /* Only raw events; filter constant is retained at its reset value. */
        if ((next & 31) != 5 && (next & 31) != 31) {
            return false;
        }
        if ((next & 0xfe0) != 0x80 || (next & 0x2f0c0000)) {
            return false;
        }
        if (next & BIT(28)) {
            s->edges[i] = 0;
        }
        next &= ~BIT(28); /* IRQRESET is a self-clearing command. */
    } else if (w->kind < 2) {
        if (*value & ~LINES) {
            return false;
        }
    } else if ((next & (reg ? ~0xffU : ~1U)) ||
               (reg && (next & 0xc) == 0xc)) {
        return false;
    }
    *target = next;
    gpio_update(s);
    return true;
}

static MemTxResult gpio_read(void *opaque, hwaddr addr, uint64_t *value,
                             unsigned size, MemTxAttrs attrs)
{
    uint32_t data = UINT32_MAX;
    bool valid = gpio_access(opaque, addr, &data, false);
    *value = data;
    trace_rp1_gpio_access(false, ((RP1GPIOWindow *)opaque)->kind, addr,
                          data, valid);
    return valid ? MEMTX_OK : MEMTX_ERROR;
}

static MemTxResult gpio_write(void *opaque, hwaddr addr, uint64_t value,
                              unsigned size, MemTxAttrs attrs)
{
    uint32_t data = value;
    bool valid = gpio_access(opaque, addr, &data, true);
    trace_rp1_gpio_access(true, ((RP1GPIOWindow *)opaque)->kind, addr,
                          value, valid);
    if (!valid) {
        qemu_log_mask(LOG_GUEST_ERROR, "rp1-gpio: unsupported write @0x%"
                      HWADDR_PRIx " = 0x%" PRIx64 "\n", addr, value);
    }
    return valid ? MEMTX_OK : MEMTX_ERROR;
}

static const MemoryRegionOps gpio_ops = {
    .read_with_attrs = gpio_read, .write_with_attrs = gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void gpio_reset(DeviceState *dev)
{
    RP1GPIOState *s = RP1_GPIO(dev);
    unsigned i;

    for (i = 0; i < 2; i++) {
        s->ctrl[i] = 0x9f; /* NULL function, filter M=4. */
        s->pads[i] = 0x92; /* Documented fixed fields; lab pull default=none. */
        s->edges[i] = 0;
        s->sample[i] = false;
    }
    s->out = s->oe = s->input = s->inte = s->intf = s->voltage = 0;
    gpio_update(s);
}

static void gpio_init(Object *obj)
{
    RP1GPIOState *s = RP1_GPIO(obj);
    unsigned i;
    for (i = 0; i < 3; i++) {
        s->windows[i].owner = s;
        s->windows[i].kind = i;
        memory_region_init_io(&s->windows[i].mmio, obj, &gpio_ops,
                              &s->windows[i], "rp1-gpio-window", 0xc000);
    }
    s->clock_running = true;
    qdev_init_gpio_out(DEVICE(obj), &s->irq, 1);
}

static const VMStateDescription gpio_vmstate = {
    .name = TYPE_RP1_GPIO, .unmigratable = 1,
};

static void gpio_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    device_class_set_legacy_reset(dc, gpio_reset);
    dc->user_creatable = false;
    dc->vmsd = &gpio_vmstate;
}

static const TypeInfo gpio_type = {
    .name = TYPE_RP1_GPIO, .parent = TYPE_DEVICE,
    .instance_size = sizeof(RP1GPIOState),
    .instance_init = gpio_init, .class_init = gpio_class_init,
};
static void gpio_register_types(void)
{
    type_register_static(&gpio_type);
}
type_init(gpio_register_types)

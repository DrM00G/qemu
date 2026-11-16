/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local RP1 GPIO experiment; not for upstream submission. */
#ifndef HW_RP1_GPIO_H
#define HW_RP1_GPIO_H
#include "hw/core/qdev.h"
#include "system/memory.h"
#define TYPE_RP1_GPIO "rp1-gpio-lab"
OBJECT_DECLARE_SIMPLE_TYPE(RP1GPIOState, RP1_GPIO)
typedef struct RP1GPIOWindow {
    MemoryRegion mmio;
    RP1GPIOState *owner;
    unsigned kind;
} RP1GPIOWindow;
struct RP1GPIOState {
    DeviceState parent_obj;
    RP1GPIOWindow windows[3];
    qemu_irq irq;
    uint32_t ctrl[2], pads[2], edges[2];
    uint32_t out, oe, input, inte, intf, voltage;
    bool sample[2], irq_level, clock_running;
};
void rp1_gpio_set_clock(RP1GPIOState *s, bool running);
#endif

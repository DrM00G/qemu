/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * BCM2712 MSI-X Interrupt Peripheral, public Linux driver edge-mode subset.
 * Source contract: drivers/irqchip/irq-bcm2712-mip.c and bcm2712.dtsi.
 * AI-assisted local research, not intended for upstream submission.
 *
 * No public reset/level/VPU/clear-status specification was found. Reset is
 * conservatively masked; only the driver's unmasked host edge mode delivers.
 * Status is quiescent for that mode. INT_CLEAR is deliberately unimplemented:
 * The real edge driver acknowledges at the parent GIC.
 */
#include "qemu/osdep.h"
#include "hw/intc/bcm2712-mip.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/pci/msi.h"
#include "migration/vmstate.h"
#include "qapi/error.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "trace.h"

static void mip_raise(BCM2712MIPState *s, uint32_t vector)
{
    bool valid = vector >= s->first_vector &&
                 vector - s->first_vector < s->num_vectors;
    bool deliver = valid && !(s->mask_host & (UINT64_C(1) << vector)) &&
                   (s->edge & (UINT64_C(1) << vector));

    trace_bcm2712_mip_raise(s->first_vector, vector, deliver);
    if (deliver) {
        qemu_irq_pulse(s->irq[vector - s->first_vector]);
    } else if (valid && !(s->edge & (UINT64_C(1) << vector))) {
        qemu_log_mask(LOG_UNIMP,
                      "bcm2712-mip: level mode is not implemented\n");
    }
}

static uint64_t mip_read(void *opaque, hwaddr addr, unsigned size)
{
    BCM2712MIPState *s = opaque;
    uint32_t value = 0;

    switch (addr) {
    case 0x20:
        value = s->edge;
        break;
    case 0x30:
        value = s->edge >> 32;
        break;
    case 0x40:
        value = s->mask_host;
        break;
    case 0x50:
        value = s->mask_host >> 32;
        break;
    case 0x60:
        value = s->mask_vpu;
        break;
    case 0x70:
        value = s->mask_vpu >> 32;
        break;
    case 0x80: /* Host status: supported edge outputs are pulses. */
    case 0x90:
    case 0xa0: /* VPU delivery not implemented. */
    case 0xb0:
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "bcm2712-mip: unknown read @0x%"
                      HWADDR_PRIx "\n", addr);
    }
    trace_bcm2712_mip_mmio(false, addr, value);
    return value;
}

static void mip_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    BCM2712MIPState *s = opaque;
    uint64_t *reg;
    unsigned shift = (addr & 0x10) ? 32 : 0;

    trace_bcm2712_mip_mmio(true, addr, value);
    switch (addr) {
    case 0:
        mip_raise(s, value);
        return;
    case 0x20:
    case 0x30:
        reg = &s->edge;
        break;
    case 0x40:
    case 0x50:
        reg = &s->mask_host;
        break;
    case 0x60:
    case 0x70:
        reg = &s->mask_vpu;
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "bcm2712-mip: unimplemented write @0x%"
                      HWADDR_PRIx " = 0x%" PRIx64 "\n", addr, value);
        return;
    }
    *reg = (*reg & ~(UINT64_C(0xffffffff) << shift)) |
           ((value & 0xffffffff) << shift);
}

static void mip_doorbell_write(void *opaque, hwaddr addr,
                               uint64_t value, unsigned size)
{
    if (!addr) {
        mip_raise(opaque, value);
    } else {
        qemu_log_mask(LOG_UNIMP, "bcm2712-mip: unknown MSI offset 0x%"
                      HWADDR_PRIx "\n", addr);
    }
}

static const MemoryRegionOps mip_ops = {
    .read = mip_read, .write = mip_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static const MemoryRegionOps mip_doorbell_ops = {
    .write = mip_doorbell_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void mip_reset(DeviceState *dev)
{
    BCM2712MIPState *s = BCM2712_MIP(dev);
    unsigned i;

    s->edge = 0;
    s->mask_host = s->mask_vpu = UINT64_MAX;
    for (i = 0; i < s->num_vectors; i++) {
        qemu_set_irq(s->irq[i], 0);
    }
}

static void mip_realize(DeviceState *dev, Error **errp)
{
    BCM2712MIPState *s = BCM2712_MIP(dev);
    unsigned i;

    if (!s->num_vectors || s->first_vector >= 64 ||
        s->num_vectors > 64 - s->first_vector) {
        error_setg(errp, "bcm2712-mip: vector range must fit 0..63");
        return;
    }
    for (i = 0; i < s->num_vectors; i++) {
        sysbus_init_irq(SYS_BUS_DEVICE(dev), &s->irq[i]);
    }
    msi_nonbroken = true;
}

static void mip_init(Object *obj)
{
    BCM2712MIPState *s = BCM2712_MIP(obj);

    memory_region_init_io(&s->regs, obj, &mip_ops, s, "mip-registers", 0xc0);
    memory_region_init_io(&s->doorbell, obj, &mip_doorbell_ops, s,
                          "mip-msi-doorbell", 0x1000);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->regs);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->doorbell);
}

static const Property mip_props[] = {
    DEFINE_PROP_UINT32("first-vector", BCM2712MIPState, first_vector, 0),
    DEFINE_PROP_UINT32("num-vectors", BCM2712MIPState, num_vectors, 64),
};

static const VMStateDescription mip_vmstate = {
    .name = TYPE_BCM2712_MIP,
    .unmigratable = 1,
};

static void mip_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = mip_realize;
    dc->vmsd = &mip_vmstate;
    device_class_set_props(dc, mip_props);
    device_class_set_legacy_reset(dc, mip_reset);
}

static const TypeInfo mip_type = {
    .name = TYPE_BCM2712_MIP,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(BCM2712MIPState),
    .instance_init = mip_init,
    .class_init = mip_class_init,
};

static void mip_register_types(void)
{
    type_register_static(&mip_type);
}
type_init(mip_register_types)

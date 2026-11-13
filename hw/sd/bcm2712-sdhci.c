/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Experimental BCM2712 SDHCI wrapper. AI-assisted local research only.
 * Implements the configuration contract of Raspberry Pi Linux's
 * sdhci-brcmstb BCM2712 path, around QEMU's existing SDHCI/eMMC engine.
 * PIO only; no PHY, tuning, CQE, SD Express or electrical timing model.
 * Configuration reset values are simulated, not measured silicon values.
 */
#include "qemu/osdep.h"
#include "hw/sd/bcm2712-sdhci.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "qapi/error.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "trace.h"

static uint64_t bcm2712_cfg_read(void *opaque, hwaddr offset, unsigned size)
{
    BCM2712SDHCIState *s = opaque;
    uint32_t value = 0;

    switch (offset) {
    case 0:
        value = s->ctrl;
        break;
    case 0x44:
        value = s->pin_sel;
        break;
    case 0x4c:
        value = s->cq_cap;
        break;
    case 0x1ac:
        value = s->max50;
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "bcm2712-sdhci: cfg read 0x%" HWADDR_PRIx
                      " unimplemented\n", offset);
    }
    trace_bcm2712_sdhci_cfg(false, offset, value);
    return value;
}

static void bcm2712_cfg_write(void *opaque, hwaddr offset, uint64_t value,
                              unsigned size)
{
    BCM2712SDHCIState *s = opaque;

    trace_bcm2712_sdhci_cfg(true, offset, value);
    switch (offset) {
    /* Driver's forced card-detect override; card is nonremovable. */
    case 0:
        s->ctrl = value & 0xc0000000;
        break;
    /* SD/MMC clock-source selection, without physical PHY behavior. */
    case 0x44:
        s->pin_sel = value & 3;
        break;
    /* Timer descriptor only, does not enable command queuing. */
    case 0x4c:
        s->cq_cap = value & 0x3fff;
        break;
    case 0x1ac:
        s->max50 = value & 0x80000001;
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "bcm2712-sdhci: cfg write 0x%" HWADDR_PRIx
                      " unimplemented\n", offset);
    }
}

static const MemoryRegionOps bcm2712_cfg_ops = {
    .read = bcm2712_cfg_read,
    .write = bcm2712_cfg_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void bcm2712_sdhci_reset(DeviceState *dev)
{
    BCM2712SDHCIState *s = BCM2712_SDHCI(dev);

    s->ctrl = s->pin_sel = s->cq_cap = 0;
    s->max50 = 1;
}

static void bcm2712_sdhci_realize(DeviceState *dev, Error **errp)
{
    BCM2712SDHCIState *s = BCM2712_SDHCI(dev);
    SysBusDevice *core = SYS_BUS_DEVICE(&s->core);

    if (!sysbus_realize(core, errp)) {
        return;
    }
    memory_region_init(&s->host, OBJECT(s), "bcm2712-sdhci.host", 0x260);
    memory_region_add_subregion(&s->host, 0, sysbus_mmio_get_region(core, 0));
    sysbus_init_mmio(SYS_BUS_DEVICE(s), &s->host);
    memory_region_init_io(&s->cfg, OBJECT(s), &bcm2712_cfg_ops, s,
                          "bcm2712-sdhci.cfg", 0x200);
    sysbus_init_mmio(SYS_BUS_DEVICE(s), &s->cfg);
    sysbus_pass_irq(SYS_BUS_DEVICE(s), core);
}

static void bcm2712_sdhci_init(Object *obj)
{
    BCM2712SDHCIState *s = BCM2712_SDHCI(obj);

    object_initialize_child(obj, "core", &s->core, TYPE_SYSBUS_SDHCI);
    qdev_prop_set_uint8(DEVICE(&s->core), "sd-spec-version", 3);
    qdev_prop_set_bit(DEVICE(&s->core), "x-auto-cmd23", true);
    /* Embedded 8-bit, 200MHz base, 1MHz timeout, 3.3V, PIO/legacy only. */
    qdev_prop_set_uint64(DEVICE(&s->core), "capareg", 0x0104c881);
}

static const VMStateDescription bcm2712_sdhci_vmstate = {
    .name = TYPE_BCM2712_SDHCI,
    .unmigratable = true,
};

static void bcm2712_sdhci_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = bcm2712_sdhci_realize;
    device_class_set_legacy_reset(dc, bcm2712_sdhci_reset);
    dc->desc = "Experimental BCM2712 SDHCI (PIO subset)";
    dc->user_creatable = false;
    dc->vmsd = &bcm2712_sdhci_vmstate;
}

static const TypeInfo bcm2712_sdhci_type = {
    .name = TYPE_BCM2712_SDHCI,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(BCM2712SDHCIState),
    .instance_init = bcm2712_sdhci_init,
    .class_init = bcm2712_sdhci_class_init,
};

static void bcm2712_sdhci_register(void)
{
    type_register_static(&bcm2712_sdhci_type);
}
type_init(bcm2712_sdhci_register)

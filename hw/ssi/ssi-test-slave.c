/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Deterministic SSI fixture: response = TX XOR xor-mask. Local AI research. */
#include "qemu/osdep.h"
#include "hw/ssi/ssi.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "qemu/module.h"

#define TYPE_SSI_TEST_SLAVE "ssi-test-slave"
OBJECT_DECLARE_SIMPLE_TYPE(SSITestSlave, SSI_TEST_SLAVE)

struct SSITestSlave {
    SSIPeripheral parent_obj;
    uint32_t xor_mask;
};

static uint32_t test_slave_transfer(SSIPeripheral *dev, uint32_t val)
{
    return val ^ SSI_TEST_SLAVE(dev)->xor_mask;
}

static void test_slave_realize(SSIPeripheral *dev, Error **errp)
{
}

static const Property test_slave_props[] = {
    DEFINE_PROP_UINT32("xor-mask", SSITestSlave, xor_mask, 0xa5),
};

static const VMStateDescription test_slave_vmstate = {
    .name = TYPE_SSI_TEST_SLAVE,
    .unmigratable = 1,
};

static void test_slave_class_init(ObjectClass *klass, const void *data)
{
    SSIPeripheralClass *ssc = SSI_PERIPHERAL_CLASS(klass);
    DeviceClass *dc = DEVICE_CLASS(klass);

    ssc->transfer = test_slave_transfer;
    ssc->realize = test_slave_realize;
    ssc->cs_polarity = SSI_CS_LOW;
    dc->vmsd = &test_slave_vmstate;
    device_class_set_props(dc, test_slave_props);
}

static const TypeInfo test_slave_type = {
    .name = TYPE_SSI_TEST_SLAVE,
    .parent = TYPE_SSI_PERIPHERAL,
    .instance_size = sizeof(SSITestSlave),
    .class_init = test_slave_class_init,
};

static void test_slave_register_types(void)
{
    type_register_static(&test_slave_type);
}
type_init(test_slave_register_types)

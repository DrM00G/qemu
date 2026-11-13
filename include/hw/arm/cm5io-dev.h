/* SPDX-License-Identifier: GPL-2.0-or-later */
/* AI-assisted local research; not intended for upstream submission. */
#ifndef HW_ARM_CM5IO_DEV_H
#define HW_ARM_CM5IO_DEV_H

/* BCM2712 addresses from Raspberry Pi Linux bcm2712.dtsi. */
#define CM5_GIC_DIST       0x107fff9000ULL
#define CM5_GIC_CPU        0x107fffa000ULL
#define CM5_UART10         0x107d001000ULL
#define CM5_RP1_WINDOW     0x1f00000000ULL
#define CM5_MIP0           0x1000130000ULL
#define CM5_MIP1           0x1000131000ULL
#define CM5_MIP_MSI        0xfffffff000ULL
#define CM5_EMMC_HOST      0x1000fff000ULL
#define CM5_EMMC_CFG       0x1000fff400ULL
#define CM5_EMMC_IRQ       273

/* Explicitly experimental generic substitutes, NOT BCM2712 register blocks. */
#define CM5_RP1_ECAM       0x1200000000ULL
#define CM5_EXP_ECAM       0x1201000000ULL
#define CM5_MSI_FRAME      0x1202000000ULL
#define CM5_HEADER_UART    0x1203000000ULL
#define CM5_TEST_RTC       0x1203010000ULL
#define CM5_RP1_PIO        0x1204000000ULL
#define CM5_EXP_PIO        0x1204010000ULL
#define CM5_EXP_WINDOW     0x1b00000000ULL
#define CM5_PCI_BUS_BASE   0x10000000ULL
#define CM5_PCI_SIZE       0x10000000ULL
#define CM5_ECAM_SIZE      0x01000000ULL
#define CM5_EXTERNAL_IRQS  480
#define CM5_MSI_FIRST      128
#define CM5_MSI_COUNT      128
#endif

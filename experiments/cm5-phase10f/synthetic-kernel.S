/* AI-assisted, local nonproprietary loader smoke fixture. Not Linux/firmware. */
.section .text
.global _start
_start:
    b entry
    .word 0
    .quad 0x80000
    .quad image_end - _start
    .quad 0
    .quad 0, 0, 0
    .word 0x644d5241
    .word 0
entry:
    movz x1, #0x1000
    movk x1, #0x7d00, lsl #16
    movk x1, #0x10, lsl #32
    adr x3, message
1:
    ldrb w2, [x3], #1
    cbz w2, 2f
    str w2, [x1]
    b 1b
2:
    movz x0, #8
    movk x0, #0x8400, lsl #16
    smc #0
3:
    wfi
    b 3b
message:
    .asciz "PHASE10F_SELECTED_SYNTHETIC_KERNEL_EXECUTED\n"
.balign 8
image_end:

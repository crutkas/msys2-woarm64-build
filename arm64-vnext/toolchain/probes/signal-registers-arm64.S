/* Exercise asynchronous signal return without a C call while registers are live. */
	.text
	.global signal_register_probe
	.seh_proc signal_register_probe
signal_register_probe:
	stp x29, x30, [sp, #-16]!
	.seh_save_fplr_x 16
	sub sp, sp, #1008
	.seh_stackalloc 1008
	stp x19, x20, [sp, #0]
	.seh_save_regp x19, 0
	stp x21, x22, [sp, #16]
	.seh_save_regp x21, 16
	stp x23, x24, [sp, #32]
	.seh_save_regp x23, 32
	stp x25, x26, [sp, #48]
	.seh_save_regp x25, 48
	stp x27, x28, [sp, #64]
	.seh_save_regp x27, 64
	stp d8, d9, [sp, #80]
	.seh_save_fregp d8, 80
	stp d10, d11, [sp, #96]
	.seh_save_fregp d10, 96
	stp d12, d13, [sp, #112]
	.seh_save_fregp d12, 112
	stp d14, d15, [sp, #128]
	.seh_save_fregp d14, 128
	mov x29, sp
	.seh_set_fp
	.seh_endprologue
	mrs x16, fpcr
	mrs x17, fpsr
	stp x16, x17, [sp, #144]
	stp x0, x1, [sp, #160]
	stp x2, x18, [sp, #176]

	.irp n,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,19,20,21,22,23,24,25,26,27,28
	mov x\n, #(0x1000+\n)
	.endr
	.irp n,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
	movi v\n\().16b, #(0x40+\n)
	.endr
	mov x16, #0x400000
	msr fpcr, x16
	mov x16, #1
	msr fpsr, x16
	ldr x17, [sp, #168]
	stlr w16, [x17]
	ldr x16, [sp, #176]
	mov x17, #0xa0000000
	msr nzcv, x17
1:
	ldar w17, [x16]
	cbz w17, 1b

	.irp n,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30
	str x\n, [sp, #(208+8*\n)]
	.endr
	mov x17, sp
	str x17, [sp, #456]
	mrs x17, nzcv
	str x17, [sp, #464]
	mrs x17, fpcr
	str x17, [sp, #472]
	mrs x17, fpsr
	str x17, [sp, #480]
	.irp n,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
	str q\n, [sp, #(496+16*\n)]
	.endr

	ldr x0, [sp, #160]
	add x1, sp, #208
	mov x2, #800
	bl memcpy
	/* Supply independent entry values for platform/LR checks. */
	ldr x0, [sp, #160]
	ldr x16, [sp, #184]
	str x16, [x0, #800]
	ldr x16, [sp, #1016]
	str x16, [x0, #808]
	ldp x16, x17, [sp, #144]
	msr fpcr, x16
	msr fpsr, x17
	mov w0, #0
	.seh_startepilogue
	ldp d14, d15, [sp, #128]
	.seh_save_fregp d14, 128
	ldp d12, d13, [sp, #112]
	.seh_save_fregp d12, 112
	ldp d10, d11, [sp, #96]
	.seh_save_fregp d10, 96
	ldp d8, d9, [sp, #80]
	.seh_save_fregp d8, 80
	ldp x27, x28, [sp, #64]
	.seh_save_regp x27, 64
	ldp x25, x26, [sp, #48]
	.seh_save_regp x25, 48
	ldp x23, x24, [sp, #32]
	.seh_save_regp x23, 32
	ldp x21, x22, [sp, #16]
	.seh_save_regp x21, 16
	ldp x19, x20, [sp, #0]
	.seh_save_regp x19, 0
	add sp, sp, #1008
	.seh_stackalloc 1008
	ldp x29, x30, [sp], #16
	.seh_save_fplr_x 16
	.seh_endepilogue
	ret
	.seh_endproc

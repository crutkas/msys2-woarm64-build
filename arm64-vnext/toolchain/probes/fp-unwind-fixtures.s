    .text

    .global fp_direct_nonzero
    .seh_proc fp_direct_nonzero
fp_direct_nonzero:
    sub sp, sp, #64
    .seh_stackalloc 64
    str d8, [sp, 8]
    .seh_save_freg v8, 8
    str x30, [sp]
    .seh_save_reg x30, 0
    .seh_endprologue
    nop
    .seh_startepilogue
    ldr x30, [sp]
    .seh_save_reg x30, 0
    ldr d8, [sp, 8]
    .seh_save_freg v8, 8
    add sp, sp, #64
    .seh_stackalloc 64
    ret
    .seh_endepilogue
    .seh_endproc

    .global fp_direct_zero
    .seh_proc fp_direct_zero
fp_direct_zero:
    sub sp, sp, #64
    .seh_stackalloc 64
    str d8, [sp]
    .seh_save_freg v8, 0
    .seh_endprologue
    nop
    .seh_startepilogue
    ldr d8, [sp]
    .seh_save_freg v8, 0
    add sp, sp, #64
    .seh_stackalloc 64
    ret
    .seh_endepilogue
    .seh_endproc

    .global fp_pair_nonzero
    .seh_proc fp_pair_nonzero
fp_pair_nonzero:
    sub sp, sp, #64
    .seh_stackalloc 64
    stp d8, d9, [sp, 16]
    .seh_save_fregp v8, 16
    str x30, [sp]
    .seh_save_reg x30, 0
    .seh_endprologue
    nop
    .seh_startepilogue
    ldr x30, [sp]
    .seh_save_reg x30, 0
    ldp d8, d9, [sp, 16]
    .seh_save_fregp v8, 16
    add sp, sp, #64
    .seh_stackalloc 64
    ret
    .seh_endepilogue
    .seh_endproc

    .global fp_prepost_single
    .seh_proc fp_prepost_single
fp_prepost_single:
    str d8, [sp, -16]!
    .seh_save_freg_x v8, 16
    str x30, [sp, 8]
    .seh_save_reg x30, 8
    .seh_endprologue
    nop
    .seh_startepilogue
    ldr x30, [sp, 8]
    .seh_save_reg x30, 8
    ldr d8, [sp], 16
    .seh_save_freg_x v8, 16
    ret
    .seh_endepilogue
    .seh_endproc

    .global fp_prepost_pair
    .seh_proc fp_prepost_pair
fp_prepost_pair:
    stp d8, d9, [sp, -32]!
    .seh_save_fregp_x v8, 32
    str x30, [sp, 16]
    .seh_save_reg x30, 16
    .seh_endprologue
    nop
    .seh_startepilogue
    ldr x30, [sp, 16]
    .seh_save_reg x30, 16
    ldp d8, d9, [sp], 32
    .seh_save_fregp_x v8, 32
    ret
    .seh_endepilogue
    .seh_endproc

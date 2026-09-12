        .text
        .macro prologue
        stp x29,x30,[sp,#-32]!
        .seh_save_fplr_x 32
        mov x29,sp
        .seh_set_fp
        str x19,[sp,#16]
        .seh_save_reg x19,16
        .endm
        .macro epilogue
        .seh_startepilogue
        ldr x19,[sp,#16]
        .seh_save_reg x19,16
        ldp x29,x30,[sp],#32
        .seh_save_fplr_x 32
        .seh_endepilogue
        ret
        .endm

        .seh_proc compact
compact:
        prologue
        .seh_endprologue
        mov x19,#7777
        epilogue
        .seh_endproc

        .seh_proc large_index
large_index:
        prologue
        .rept 32
        nop
        .seh_nop
        .endr
        .seh_endprologue
        mov x19,#7777
        epilogue
        .seh_endproc

        .seh_proc multiple
multiple:
        prologue
        .seh_endprologue
        cbz x0,second_epilogue
        epilogue
second_epilogue:
        epilogue
        .seh_endproc

        .seh_proc nonterminal
nonterminal:
        prologue
        .seh_endprologue
        mov x19,#7777
        epilogue
        nop
        .seh_endproc

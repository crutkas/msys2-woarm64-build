#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winnt.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern void fp_direct_nonzero(void);
extern void fp_direct_zero(void);
extern void fp_pair_nonzero(void);
extern void fp_prepost_single(void);
extern void fp_prepost_pair(void);
static void caller_marker(void) { }

typedef struct CaseSpec {
    const char *name;
    void (*fn)(void);
    DWORD64 delta;
    DWORD64 current_spoff;
    DWORD64 final_spoff;
    DWORD64 lr_slot_off;
    long long expected_lrptr_off;
    DWORD64 d8_slot_off;
    DWORD64 d9_slot_off;
    int expect_d8;
    int expect_d9;
    int expect_pc_match;
    int current_lr_is_caller;
} CaseSpec;

static int run_case(const CaseSpec *c) {
    __attribute__((aligned(16))) unsigned char stack[1024];
    memset(stack, 0xA5, sizeof(stack));
    DWORD64 caller_pc = (DWORD64)(uintptr_t)&caller_marker;
    DWORD64 saved_d8 = 0x1122334455667788ULL;
    DWORD64 saved_d9 = 0x8877665544332211ULL;
    DWORD64 wrong_pc = caller_pc ^ 0x12345678ULL;
    if (c->lr_slot_off != (DWORD64)-1) *(DWORD64 *)(void *)(stack + c->lr_slot_off) = c->expect_pc_match ? caller_pc : wrong_pc;
    if (c->expect_d8) *(DWORD64 *)(void *)(stack + c->d8_slot_off) = saved_d8;
    if (c->expect_d9) *(DWORD64 *)(void *)(stack + c->d9_slot_off) = saved_d9;
    CONTEXT ctx; KNONVOLATILE_CONTEXT_POINTERS ptrs;
    memset(&ctx, 0, sizeof(ctx)); memset(&ptrs, 0, sizeof(ptrs));
    ctx.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER | CONTEXT_FLOATING_POINT;
    ctx.Pc = (DWORD64)((uintptr_t)c->fn + c->delta);
    ctx.Sp = (DWORD64)(uintptr_t)(stack + c->current_spoff);
    ctx.Lr = c->current_lr_is_caller ? caller_pc : 0xdeadbeefcafebabeULL;
    ctx.V[8].Low = 0xaabbccddeeff0011ULL;
    ctx.V[9].Low = 0x9988776655443322ULL;
    ULONG_PTR image_base = 0, establisher = 0; void *handler = 0;
    PRUNTIME_FUNCTION entry = RtlLookupFunctionEntry(ctx.Pc, &image_base, NULL);
    if (!entry) { printf("%s:missing-runtime-function\n", c->name); return 10; }
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, image_base, ctx.Pc, entry, &ctx, &handler, &establisher, &ptrs);
    long long lrptr_off = ptrs.Lr ? (long long)((DWORD64)(uintptr_t)ptrs.Lr - (DWORD64)(uintptr_t)stack) : -1LL;
    long long d8ptr_off = ptrs.D8 ? (long long)((DWORD64)(uintptr_t)ptrs.D8 - (DWORD64)(uintptr_t)stack) : -1LL;
    long long d9ptr_off = ptrs.D9 ? (long long)((DWORD64)(uintptr_t)ptrs.D9 - (DWORD64)(uintptr_t)stack) : -1LL;
    int pc_ok = ((ctx.Pc == caller_pc) == c->expect_pc_match);
    int sp_ok = (ctx.Sp == (DWORD64)(uintptr_t)(stack + c->final_spoff));
    int lr_ok = (lrptr_off == c->expected_lrptr_off);
    int d8_ok = (!c->expect_d8) || (d8ptr_off == (long long)c->d8_slot_off && ctx.V[8].Low == saved_d8);
    int d9_ok = (!c->expect_d9) || (d9ptr_off == (long long)c->d9_slot_off && ctx.V[9].Low == saved_d9);
    if (!(pc_ok && sp_ok && lr_ok && d8_ok && d9_ok)) {
        printf("%s:fail pc_match=%d spoff=%llu/%llu lrptr=%lld/%lld d8ptr=%lld/%llu d8=%llx/%llx d9ptr=%lld/%llu d9=%llx/%llx estab=%lld\n",
               c->name, ctx.Pc == caller_pc,
               (unsigned long long)(ctx.Sp - (DWORD64)(uintptr_t)stack), (unsigned long long)c->final_spoff,
               lrptr_off, c->expected_lrptr_off,
               d8ptr_off, (unsigned long long)c->d8_slot_off, (unsigned long long)ctx.V[8].Low, (unsigned long long)saved_d8,
               d9ptr_off, (unsigned long long)c->d9_slot_off, (unsigned long long)ctx.V[9].Low, (unsigned long long)saved_d9,
               (long long)(establisher - (ULONG_PTR)(uintptr_t)stack));
        return 20;
    }
    printf("%s:ok pc_match=%d spoff=%llu lrptr=%lld d8ptr=%lld d8=%llx d9ptr=%lld d9=%llx estab=%lld\n",
           c->name, ctx.Pc == caller_pc,
           (unsigned long long)(ctx.Sp - (DWORD64)(uintptr_t)stack), lrptr_off,
           d8ptr_off, (unsigned long long)ctx.V[8].Low,
           d9ptr_off, (unsigned long long)ctx.V[9].Low,
           (long long)(establisher - (ULONG_PTR)(uintptr_t)stack));
    return 0;
}

int main(void) {
    struct { WORD machine, reserved; DWORD attributes; } machine = { 0 };
    if (!GetProcessInformation(GetCurrentProcess(), (PROCESS_INFORMATION_CLASS)9,
                               &machine, sizeof(machine)) || machine.machine != 0xaa64)
        return 11;
    int rc = 0;
    const DWORD64 none = (DWORD64)-1;
    const CaseSpec cases[] = {
        {"direct-nonzero-prolog-after-d8", fp_direct_nonzero, 8, 256, 320, 256, -1, 264, none, 1, 0, 1, 1},
        {"direct-nonzero-prolog-after-lr", fp_direct_nonzero, 12, 256, 320, 256, 256, 264, none, 1, 0, 1, 0},
        {"direct-nonzero-epilog-before-lr", fp_direct_nonzero, 16, 256, 320, 256, 256, 264, none, 1, 0, 1, 0},
        {"direct-nonzero-epilog-after-lr-before-d8", fp_direct_nonzero, 20, 256, 320, 256, -1, 264, none, 1, 0, 1, 1},
        {"direct-zero-prolog-after-d8", fp_direct_zero, 8, 256, 320, none, -1, 256, none, 1, 0, 1, 1},
        {"pair-nonzero-prolog-after-pair", fp_pair_nonzero, 8, 256, 320, 256, -1, 272, 280, 1, 1, 1, 1},
        {"pair-nonzero-prolog-after-lr", fp_pair_nonzero, 12, 256, 320, 256, 256, 272, 280, 1, 1, 1, 0},
        {"pair-nonzero-epilog-before-lr", fp_pair_nonzero, 16, 256, 320, 256, 256, 272, 280, 1, 1, 1, 0},
        {"pair-nonzero-epilog-after-lr-before-pair", fp_pair_nonzero, 20, 256, 320, 256, -1, 272, 280, 1, 1, 1, 1},
        {"prepost-single-prolog-after-d8", fp_prepost_single, 4, 256, 272, 264, -1, 256, none, 1, 0, 1, 1},
        {"prepost-single-prolog-after-lr", fp_prepost_single, 8, 256, 272, 264, 264, 256, none, 1, 0, 1, 0},
        {"prepost-single-epilog-before-lr", fp_prepost_single, 12, 256, 272, 264, 264, 256, none, 1, 0, 1, 0},
        {"prepost-single-epilog-after-lr-before-d8", fp_prepost_single, 16, 256, 272, 264, -1, 256, none, 1, 0, 1, 1},
        {"prepost-pair-prolog-after-pair", fp_prepost_pair, 4, 256, 288, 272, -1, 256, 264, 1, 1, 1, 1},
        {"prepost-pair-prolog-after-lr", fp_prepost_pair, 8, 256, 288, 272, 272, 256, 264, 1, 1, 1, 0},
        {"prepost-pair-epilog-before-lr", fp_prepost_pair, 12, 256, 288, 272, 272, 256, 264, 1, 1, 1, 0},
        {"prepost-pair-epilog-after-lr-before-pair", fp_prepost_pair, 16, 256, 288, 272, -1, 256, 264, 1, 1, 1, 1},
        {"direct-nonzero-wrong-lr-slot", fp_direct_nonzero, 12, 256, 320, 256, 256, 264, none, 1, 0, 0, 0},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); ++i) rc |= run_case(&cases[i]);
    if (rc == 0) puts("native-fp-unwind-boundaries-ok");
    return rc;
}

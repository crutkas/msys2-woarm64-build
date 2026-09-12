#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

struct snapshot {
    uint64_t x[31], sp, nzcv, fpcr, fpsr, padding;
    unsigned char q[32][16];
    uint64_t entry_platform, entry_lr;
};
_Static_assert(sizeof(struct snapshot) == 816, "Assembly snapshot layout");
static int armed, delivered, handlers;
static pthread_t target;
extern int signal_register_probe(struct snapshot *, int *, int *);

static void handler(int signo)
{
    (void)signo;
    /* The C compiler preserves the ABI-required low halves of v8-v15.
       Their upper halves and all volatile vectors deliberately change. */
    __asm__ volatile(
        "msr fpcr, xzr\nmsr fpsr, xzr\n"
        ".irp n,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31\n"
        "movi v\\n\\().16b, #0\n.endr\n"
        ::: "v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7",
            "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15",
            "v16", "v17", "v18", "v19", "v20", "v21", "v22", "v23",
            "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31", "memory");
    ++handlers;
    __atomic_store_n(&delivered, 1, __ATOMIC_RELEASE);
}

static void *sender(void *unused)
{
    (void)unused;
    while (!__atomic_load_n(&armed, __ATOMIC_ACQUIRE))
        sched_yield();
    return (void *)(intptr_t)pthread_kill(target, SIGUSR1);
}

int main(int argc, char **argv)
{
    (void)argv;
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = handler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGUSR1, &action, NULL)) {
        perror("sigaction");
        return 1;
    }
    target = pthread_self();
    for (int iteration = 0; iteration < 16; ++iteration) {
        struct snapshot actual = {0};
        pthread_t thread;
        void *result = NULL;
        __atomic_store_n(&armed, 0, __ATOMIC_RELEASE);
        __atomic_store_n(&delivered, 0, __ATOMIC_RELEASE);
        if (pthread_create(&thread, NULL, sender, NULL))
            return 2;
        signal_register_probe(&actual, &armed, &delivered);
        if (pthread_join(thread, &result) || result || handlers != iteration + 1)
            return 3;
        for (int i = 0; i < 29; ++i) {
            uint64_t expected = 0x1000 + i;
            if (i == 16)
                expected = (uintptr_t)&delivered;
            if (i == 17)
                expected = 1;
            if (i == 18)
                expected = actual.entry_platform;
            if (actual.x[i] != expected) {
                fprintf(stderr, "iteration=%d x%d=%llx expected=%llx\n", iteration, i,
                        (unsigned long long)actual.x[i], (unsigned long long)expected);
                return 4;
            }
        }
        if (actual.x[29] != actual.sp || actual.x[30] != actual.entry_lr ||
            (actual.sp & 15) || actual.nzcv != 0xa0000000 ||
            actual.fpcr != 0x400000 || actual.fpsr != 1) {
            fprintf(stderr, "control state changed: NZCV=%llx FPCR=%llx FPSR=%llx\n",
                    (unsigned long long)actual.nzcv, (unsigned long long)actual.fpcr,
                    (unsigned long long)actual.fpsr);
            return 5;
        }
        for (int reg = 0; reg < 32; ++reg)
            for (int byte = 0; byte < 16; ++byte)
                if (actual.q[reg][byte] != 0x40 + reg) {
                    fprintf(stderr, "iteration=%d q%d[%d]=%x expected=%x\n",
                            iteration, reg, byte, actual.q[reg][byte], 0x40 + reg);
                    return 6;
                }
    }
    puts("arm64-signal-registers-ok: 16 deliveries, integer/vector/control state");
    fflush(stdout);
    if (argc > 1)
        usleep(1500000);
    return 0;
}

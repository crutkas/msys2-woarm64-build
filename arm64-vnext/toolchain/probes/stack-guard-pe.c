#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern uintptr_t __stack_chk_guard;

__attribute__((noinline))
static unsigned int protected_copy(const char *text, int corrupt)
{
    volatile unsigned char local[32];
    unsigned int value = 0;
    size_t i;
    for (i = 0; i < sizeof(local); ++i) {
        local[i] = (unsigned char)text[i % 7];
        value += local[i];
    }
    if (corrupt) {
        puts("corrupting-own-process-guard");
        fflush(stdout);
        __stack_chk_guard ^= 1;
    }
    return value;
}

int main(int argc, char **argv)
{
    struct {
        WORD machine;
        WORD reserved;
        DWORD attributes;
    } info = {0};
    uintptr_t image = (uintptr_t)GetModuleHandleW(NULL);
    uintptr_t guard = (uintptr_t)&__stack_chk_guard;
    uintptr_t gap = image > guard ? image - guard : guard - image;
    unsigned int result;
    int corrupt = argc == 2 && strcmp(argv[1], "--corrupt") == 0;
    if (!GetProcessInformation(GetCurrentProcess(), (PROCESS_INFORMATION_CLASS)9,
                               &info, sizeof(info)) || info.machine != 0xaa64)
        return 10;
    if (sizeof(long) != 8 || gap <= UINT64_C(0x100000000))
        return 11;
    result = protected_copy("guard64", corrupt);
    if (corrupt) {
        puts("ERROR-guard-corruption-not-detected");
        return 12;
    }
    if (result != 2979)
        return 13;
    puts("native-msys-protected-far-guard-ok");
    return 0;
}

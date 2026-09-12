#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>

_Static_assert(sizeof(long) == 8, "Cygwin/MSYS LP64 target required");
_Static_assert(sizeof(LONG) == 4, "Win32 LONG remains 32 bits on LP64");
_Static_assert(sizeof(LONGLONG) == 8 && sizeof(void *) == 8, "Windows ARM64 widths");

int main(void)
{
    struct {
        WORD machine, reserved;
        DWORD attributes;
    } machine = {0};
    if (!GetProcessInformation(GetCurrentProcess(), (PROCESS_INFORMATION_CLASS)9,
                               &machine, sizeof(machine)) || machine.machine != 0xaa64)
        return 10;
    volatile LONG value32 = 0x12345678;
    volatile LONGLONG value64 = INT64_C(0x123456789abcdef0);
    int first, second;
    PVOID volatile pointer = &first;
    if (InterlockedExchange(&value32, -17) != 0x12345678 || value32 != -17 ||
        InterlockedExchange(&value32, INT32_MIN) != -17 || value32 != INT32_MIN ||
        InterlockedExchange(&value32, 0) != INT32_MIN || value32 != 0)
        return 11;
    if (InterlockedExchange64(&value64, -INT64_C(19)) != INT64_C(0x123456789abcdef0) ||
        value64 != -INT64_C(19) ||
        InterlockedExchange64(&value64, INT64_MIN) != -INT64_C(19) || value64 != INT64_MIN ||
        InterlockedExchange64(&value64, 0) != INT64_MIN || value64 != 0)
        return 12;
    if (InterlockedExchangePointer(&pointer, &second) != &first || pointer != &second ||
        InterlockedExchangePointer(&pointer, NULL) != &second || pointer != NULL ||
        InterlockedExchangePointer(&pointer, &first) != NULL || pointer != &first)
        return 13;
    puts("native-msys-public-interlocked-ok: 32/64/pointer previous and stored values");
    return 0;
}

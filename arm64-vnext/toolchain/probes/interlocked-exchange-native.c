#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>

_Static_assert(sizeof(LONG) == 4, "Windows LONG must be 32 bits");
_Static_assert(sizeof(LONGLONG) == 8 && sizeof(void *) == 8, "ARM64 Windows widths");

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
    void *volatile pointer = &first;
    if (_InterlockedExchange(&value32, -17) != 0x12345678 || value32 != -17 ||
        _InterlockedExchange(&value32, INT32_MIN) != -17 || value32 != INT32_MIN ||
        _InterlockedExchange(&value32, 0) != INT32_MIN || value32 != 0)
        return 11;
    if (_InterlockedExchange64(&value64, -INT64_C(19)) != INT64_C(0x123456789abcdef0) ||
        value64 != -INT64_C(19) ||
        _InterlockedExchange64(&value64, INT64_MIN) != -INT64_C(19) || value64 != INT64_MIN ||
        _InterlockedExchange64(&value64, 0) != INT64_MIN || value64 != 0)
        return 12;
    if (_InterlockedExchangePointer(&pointer, &second) != &first || pointer != &second ||
        _InterlockedExchangePointer(&pointer, NULL) != &second || pointer != NULL ||
        _InterlockedExchangePointer(&pointer, &first) != NULL || pointer != &first)
        return 13;
    puts("native-arm64-interlocked-exchange-ok: 32/64/pointer previous and stored values");
    return 0;
}

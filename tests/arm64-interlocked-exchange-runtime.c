#include <stdio.h>
#include <windows.h>

int main(void)
{
    volatile LONG value32 = 17;
    volatile LONG64 value64 = 23;
    int old_pointer_target = 31;
    int new_pointer_target = 47;
    PVOID volatile pointer_value = &old_pointer_target;

    if (InterlockedExchange(&value32, 19) != 17 || value32 != 19) {
        return 1;
    }

    if (InterlockedExchange64(&value64, 29) != 23 || value64 != 29) {
        return 2;
    }

    if (InterlockedExchangePointer(&pointer_value, &new_pointer_target) !=
            &old_pointer_target ||
        pointer_value != &new_pointer_target) {
        return 3;
    }

    puts("interlocked-exchange-runtime-ok");
    return 0;
}

#include <windows.h>

LONG exchange_public_32(volatile LONG *target, LONG value)
{
    return InterlockedExchange(target, value);
}

LONGLONG exchange_public_64(volatile LONGLONG *target, LONGLONG value)
{
    return InterlockedExchange64(target, value);
}

PVOID exchange_public_pointer(PVOID volatile *target, PVOID value)
{
    return InterlockedExchangePointer(target, value);
}

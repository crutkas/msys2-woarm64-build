#define __MINGW_EXTENSION
#define __MINGW_INTRIN_INLINE static __inline__ __attribute__((always_inline))
#define __INTRINSIC_ONLYSPECIAL
#define __INTRINSIC_SPECIAL__InterlockedExchange
#define __INTRINSIC_SPECIAL__InterlockedExchange64
#define __INTRINSIC_SPECIAL__InterlockedExchangePointer
#define __LONG32 int
#define __int64 long long

#include <psdk_inc/intrin-impl.h>

int exchange_int(volatile int *target, int value)
{
    return _InterlockedExchange(target, value);
}

long long exchange_int64(volatile long long *target, long long value)
{
    return _InterlockedExchange64(target, value);
}

void *exchange_pointer(void *volatile *target, void *value)
{
    return _InterlockedExchangePointer(target, value);
}

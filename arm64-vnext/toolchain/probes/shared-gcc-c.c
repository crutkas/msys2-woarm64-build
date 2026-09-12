#include <windows.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <omp.h>

static volatile __int128 numerator = (((__int128)1) << 100) + 9;
static volatile __int128 divisor = 3;
static _Atomic(__int128) wide;

int main(int argc, char **argv)
{
    __int128 quotient = numerator / divisor;
    __int128 remainder = numerator % divisor;
    __int128 expected = 0;
    int total = 0;
    (void)argv;
    if (quotient * divisor + remainder != numerator)
        return 10;
    if (!atomic_compare_exchange_strong(&wide, &expected, numerator) ||
        atomic_load(&wide) != numerator)
        return 11;
    omp_set_num_threads(2);
    #pragma omp parallel reduction(+:total)
    {
        for (int i = 0; i < 1000; ++i)
            atomic_fetch_add(&wide, 1);
        total += 21;
    }
    if (total != 42 || atomic_load(&wide) != numerator + 2000)
        return 12;
    puts("native-msys-shared-gcc-c-ok");
    fflush(stdout);
    if (argc > 1)
        Sleep(1500);
    return 0;
}

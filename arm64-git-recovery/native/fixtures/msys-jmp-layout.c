#include <setjmp.h>

#if !defined(__MSYS__) || !defined(__aarch64__)
#error This layout contract requires the native MSYS ARM64 target.
#endif

_Static_assert(sizeof(jmp_buf) == 256,
               "MSYS ARM64 jmp_buf must match the coherent 256-byte runtime ABI");
_Static_assert(sizeof(sigjmp_buf) >= 272,
               "MSYS ARM64 sigjmp_buf must retain its flag and mask after offset 256");

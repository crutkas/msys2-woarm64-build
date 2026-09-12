#include "target.h"

#if !defined(__MSYS__) || !defined(__aarch64__)
#error This control requires the native ARM64 MSYS compiler target.
#endif

int perl_system_link_control(void)
{
    return PERL_SYSTEM_LINK_VALUE + 1;
}

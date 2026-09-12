#if !defined(__aarch64__) || !defined(__CYGWIN__) || !defined(__MSYS__)
#error This package requires the qualified native ARM64 MSYS target.
#endif

_Static_assert(sizeof(long) == 8, "The MSYS target must use LP64.");

int pipeline_value(void)
{
    return 42;
}

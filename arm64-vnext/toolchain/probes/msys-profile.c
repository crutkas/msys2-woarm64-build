#ifndef __MSYS__
#error MSYS application profile must define __MSYS__
#endif
#ifndef __CYGWIN__
#error MSYS application profile must retain the Cygwin ABI
#endif
_Static_assert(sizeof(long) == 8, "MSYS LP64");
int main(void) { return 0; }

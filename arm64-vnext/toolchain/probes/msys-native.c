#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#ifndef __MSYS__
#error The compiler must select its MSYS application profile by default
#endif
_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS ARM64 LP64");

int main(int argc, char **argv)
{
  if (argc != 2 || getpid() <= 0)
    return 11;
  void *module = dlopen(argv[1], RTLD_NOW);
  if (!module) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 12;
  }
  int (*answer)(void) = (int (*)(void))dlsym(module, "msys_module_answer");
  if (!answer || answer() != 42)
    return 13;
  if (dlclose(module) != 0)
    return 14;
  printf("native-msys-c-ok long=%lu\n", (unsigned long)sizeof(long));
  return 0;
}

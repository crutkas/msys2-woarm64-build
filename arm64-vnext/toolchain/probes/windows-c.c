#include <stdio.h>
#include <windows.h>
#include <stdarg.h>

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 4, "Windows ARM64 LLP64");
_Static_assert(sizeof(va_list) == sizeof(char *), "Windows pointer va_list");

struct pair { unsigned long long first, second; };
__attribute__((noinline, noclone))
static int named_split(unsigned long long a, unsigned long long b,
                       unsigned long long c, unsigned long long d,
                       unsigned long long e, unsigned long long f,
                       unsigned long long g, struct pair value, ...)
{
  va_list args;
  va_start(args, value);
  unsigned long long tail = va_arg(args, unsigned long long);
  va_end(args);
  return a + b + c + d + e + f + g == 21 &&
         value.first == 7 && value.second == 8 && tail == 9;
}

int main(void)
{
  volatile unsigned long long value = 123456789;
  if (value * 17 + 9 != 2098765422ULL)
    return 21;
  HMODULE module = GetModuleHandleW(NULL);
  HRSRC resource = FindResourceW(module, MAKEINTRESOURCEW(1), MAKEINTRESOURCEW(10));
  if (!resource || SizeofResource(module, resource) != 4)
    return 22;
  const unsigned short *data = LockResource(LoadResource(module, resource));
  if (!data || data[0] != 73 || data[1] != 0xaa64)
    return 23;
  struct pair value_pair = { 7, 8 };
  if (!named_split(0, 1, 2, 3, 4, 5, 6, value_pair, 9ULL))
    return 24;
  printf("native-%s-%u\n", "printf", 73U);
  puts("native-c-ok");
  return 0;
}

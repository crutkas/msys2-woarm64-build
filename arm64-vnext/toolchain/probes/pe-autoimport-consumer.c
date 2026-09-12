#include <windows.h>
#include <stdint.h>
#include <stdio.h>

extern volatile unsigned long long autoimport_value;
extern volatile unsigned long long autoimport_array[];

int main(void)
{
  HMODULE provider = GetModuleHandleW(L"provider.dll");
  volatile unsigned long long *actual =
    (volatile unsigned long long *)GetProcAddress(provider, "autoimport_value");
  volatile unsigned long long *array =
    (volatile unsigned long long *)GetProcAddress(provider, "autoimport_array");
  if (!actual || !array || actual != &autoimport_value || array + 3 != &autoimport_array[3])
    return 41;
  uintptr_t image = (uintptr_t)GetModuleHandleW(NULL);
  uintptr_t address = (uintptr_t)actual;
  uintptr_t gap = image > address ? image - address : address - image;
  if (gap <= 0x100000000ULL)
    return 42;
  if (autoimport_value != 0x123456789abcdef0ULL || autoimport_array[3] != 44)
    return 43;
  autoimport_value = 0xfedcba9876543210ULL;
  autoimport_array[3] = 73;
  if (*actual != 0xfedcba9876543210ULL || array[3] != 73)
    return 44;
  printf("far-autoimport-ok gap=%llu\n", (unsigned long long)gap);
  return 0;
}

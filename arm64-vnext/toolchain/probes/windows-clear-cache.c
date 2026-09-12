#include <windows.h>
#include <stdint.h>
#include <stdio.h>

typedef int (*generated_function)(void);

int main(void)
{
  struct {
    WORD machine;
    WORD reserved;
    DWORD attributes;
  } machine = { 0 };
  if (!GetProcessInformation(GetCurrentProcess(),
                             (PROCESS_INFORMATION_CLASS)9,
                             &machine, sizeof(machine)) || machine.machine != 0xaa64)
    return 11;

  SYSTEM_INFO system;
  GetSystemInfo(&system);
  SIZE_T bytes = (SIZE_T)system.dwPageSize * 2;
  unsigned char *memory = VirtualAlloc(NULL, bytes, MEM_RESERVE | MEM_COMMIT,
                                       PAGE_EXECUTE_READWRITE);
  if (!memory)
    return 12;
  volatile uint32_t *code = (volatile uint32_t *)(memory + system.dwPageSize - 4);
  generated_function execute = (generated_function)(void *)code;
  code[1] = 0xd65f03c0U; /* ret */
  puts("before-clear-cache");
  fflush(stdout);
  for (unsigned value = 1; value <= 512; ++value) {
    code[0] = 0x52800000U | (value << 5); /* mov w0, #value */
    __builtin___clear_cache((char *)code, (char *)code + 8);
    if (execute() != (int)value) {
      VirtualFree(memory, 0, MEM_RELEASE);
      return 13;
    }
  }
  __builtin___clear_cache((char *)code, (char *)code);
  __builtin___clear_cache(NULL, NULL);
  if (!VirtualFree(memory, 0, MEM_RELEASE))
    return 14;
  puts("clear-cache-native-ok iterations=512 cross-page=1");
  return 0;
}

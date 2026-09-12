#include <windows.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
  struct {
    WORD machine;
    WORD reserved;
    DWORD attributes;
  } machine = { 0 };
  if (!GetProcessInformation(GetCurrentProcess(), (PROCESS_INFORMATION_CLASS)9,
                             &machine, sizeof(machine)) || machine.machine != 0xaa64)
    return 10;
  HMODULE image = GetModuleHandleW(NULL);
  HRSRC text = FindResourceW(image, MAKEINTRESOURCEW(1), MAKEINTRESOURCEW(10));
  HRSRC numbers = FindResourceW(image, MAKEINTRESOURCEW(2), MAKEINTRESOURCEW(10));
  if (!text || !numbers || SizeofResource(image, text) != 4 ||
      SizeofResource(image, numbers) != 6)
    return 11;
  const char *value = LockResource(LoadResource(image, text));
  const unsigned short *version = LockResource(LoadResource(image, numbers));
  if (!value || !version || memcmp(value, "1.19", 4) ||
      version[0] != 1 || version[1] != 19 || version[2] != 0)
    return 12;
  puts("native-windres-quoted-ok");
  return 0;
}

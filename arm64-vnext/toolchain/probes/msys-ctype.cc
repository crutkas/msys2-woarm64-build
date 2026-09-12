#include <ctype.h>
#include <iostream>
#include <locale>
#include <windows.h>

#if !defined(__MSYS__) || !defined(__CYGWIN__)
#error This consumer requires the default MSYS application profile
#endif
static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS ARM64 LP64");

int main()
{
  struct {
    WORD machine;
    WORD reserved;
    DWORD attributes;
  } machine = {};
  if (!GetProcessInformation(GetCurrentProcess(), static_cast<PROCESS_INFORMATION_CLASS>(9),
                             &machine, sizeof(machine)) || machine.machine != 0xaa64)
    return 10;
  const std::ctype<char>::mask *table = std::ctype<char>::classic_table();
  if (table != _ctype_ + 1 || _ctype_[0] != 0)
    return 11;
  if (!(table['A'] & std::ctype_base::upper) ||
      !(table['a'] & std::ctype_base::lower) ||
      !(table['9'] & std::ctype_base::digit) ||
      !(table[' '] & std::ctype_base::space))
    return 12;
  const std::ctype<char> &facet = std::use_facet<std::ctype<char>>(std::locale::classic());
  for (unsigned i = 0; i < 256; ++i) {
    if (facet.is(std::ctype_base::alpha, static_cast<char>(i)) !=
        ((table[i] & std::ctype_base::alpha) != 0))
      return 13;
  }
  std::cout << "native-msys-ctype-ok 73\n";
  return std::cout ? 0 : 14;
}

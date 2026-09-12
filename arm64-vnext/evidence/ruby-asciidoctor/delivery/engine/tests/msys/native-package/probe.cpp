#include <cstdio>
#include <locale>
#include <vector>
#include <windows.h>

#if !defined(__aarch64__) || !defined(__CYGWIN__) || !defined(__MSYS__)
#error This package requires the qualified native ARM64 MSYS C++ target.
#endif

static_assert(sizeof(long) == 8, "The MSYS target must use LP64.");
extern "C" int pipeline_value(void);

int main()
{
    const std::vector<int> values{pipeline_value(), 8};
    const auto& facet = std::use_facet<std::ctype<char>>(std::locale::classic());
    if (values[0] + values[1] != 50 || !facet.is(std::ctype_base::space, ' '))
        return 1;
    const HMODULE runtime = GetModuleHandleW(L"msys-2.0.dll");
    char path[MAX_PATH];
    const DWORD length = GetModuleFileNameA(runtime, path, MAX_PATH);
    if (!runtime || !length || length >= MAX_PATH)
        return 2;
    std::printf("MSYS_RUNTIME=%s\n", path);
    std::puts("PASS: native ARM64 MSYS C/C++ LP64 locale package reached main");
    return 0;
}

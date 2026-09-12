#include <windows.h>
#include <stdio.h>
#include <wchar.h>

int wmain(int argc, wchar_t **argv)
{
    int files = argc > 1 && wcscmp(argv[1], L"--check-files") == 0;
    for (int index = files ? 2 : 1; index < argc; ++index) {
        if (files) {
            if (GetFileAttributesW(argv[index]) == INVALID_FILE_ATTRIBUTES)
                return 2;
            puts("file-ok");
        } else {
            size_t length = wcslen(argv[index]);
            printf("%llu:", (unsigned long long)length);
            for (size_t unit = 0; unit < length; ++unit)
                printf("%04x", (unsigned int)(unsigned short)argv[index][unit]);
            putchar('\n');
        }
    }
    return 0;
}

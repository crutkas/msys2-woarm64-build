#include <stdio.h>
#include <wchar.h>
#ifndef UNICODE
#error -municode must define UNICODE
#endif

int wmain(int argc, wchar_t **argv)
{
  if (argc != 2 || wcscmp(argv[1], L"arm64-unicode") != 0)
    return 31;
  wprintf(L"%ls-%ls\n", L"native-unicode", L"ok");
  return 0;
}

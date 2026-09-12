#include <windows.h>
#include <stdio.h>

int wmain(int argc, wchar_t **argv)
{
    DWORD in_mode = 0, out_mode = 0;
    HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
    HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
    int in_console = GetConsoleMode(in, &in_mode);
    int out_console = GetConsoleMode(out, &out_mode);
    if (argc != 2)
        return 2;
    FILE *report = _wfopen(argv[1], L"wb");
    if (!report)
        return 3;
    fprintf(report, "{\"stdin_console\":%d,\"stdout_console\":%d,"
            "\"stdin_type\":%lu,\"stdout_type\":%lu,\"stdin_mode\":%lu,\"stdout_mode\":%lu}\n",
            in_console, out_console, GetFileType(in), GetFileType(out), in_mode, out_mode);
    return fclose(report) != 0;
}

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>

static LONG WINAPI report_exception(EXCEPTION_POINTERS *exception)
{
    MEMORY_BASIC_INFORMATION info;
    void *address = exception->ExceptionRecord->ExceptionAddress;
    fprintf(stderr, "exception=%08lx address=%p\n",
            exception->ExceptionRecord->ExceptionCode, address);
    if (VirtualQuery(address, &info, sizeof(info)) == sizeof(info)) {
        wchar_t module[32768];
        DWORD length = GetModuleFileNameW((HMODULE)info.AllocationBase, module, 32768);
        if (length)
            fprintf(stderr, "module=%ls offset=%llx\n", module,
                    (unsigned long long)((char *)address - (char *)info.AllocationBase));
        if (info.State == MEM_COMMIT && !(info.Protect & (PAGE_GUARD | PAGE_NOACCESS)))
            fprintf(stderr, "instruction=%08lx\n", *(const unsigned long *)address);
    }
    fflush(stderr);
    return EXCEPTION_EXECUTE_HANDLER;
}

int main(void)
{
    int error, result;
    PCRE2_SIZE offset;
    PCRE2_SPTR text = (PCRE2_SPTR)"the quick brown fox";
    SetUnhandledExceptionFilter(report_exception);
    fputs("before-compile\n", stdout);
    fflush(stdout);
    pcre2_code *code = pcre2_compile(text, PCRE2_ZERO_TERMINATED, 0, &error, &offset, NULL);
    if (!code)
        return 10;
    fputs("before-jit-compile\n", stdout);
    fflush(stdout);
    result = pcre2_jit_compile(code, PCRE2_JIT_COMPLETE);
    fprintf(stdout, "after-jit-compile=%d\n", result);
    fflush(stdout);
    if (result)
        return 11;
    pcre2_match_data *match = pcre2_match_data_create_from_pattern(code, NULL);
    if (!match)
        return 12;
    fputs("before-jit-match\n", stdout);
    fflush(stdout);
    result = pcre2_match(code, text, 19, 0, 0, match, NULL);
    fprintf(stdout, "after-jit-match=%d\n", result);
    pcre2_match_data_free(match);
    pcre2_code_free(code);
    return result == 1 ? 0 : 13;
}

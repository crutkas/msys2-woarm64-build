#include <stdio.h>
enum { ms_stdio_ansi_at_include = __USE_MINGW_ANSI_STDIO };
#include <wchar.h>
#include <stdarg.h>
#include <errno.h>
#include <windows.h>

static int write_metadata(const unsigned *data, DWORD size)
{
  DWORD written = 0;
  return WriteFile(GetStdHandle(STD_ERROR_HANDLE), data, size, &written, NULL)
         && written == size;
}

__attribute__((noinline))
static int narrow_list(unsigned api, const char *format, ...)
{
  va_list ap;
  va_start(ap, format);
  int result;
  switch (api) {
    case 1: result = vfprintf(stdout, format, ap); break;
    case 2: result = vprintf(format, ap); break;
    default:
      result = __stdio_common_vfprintf(_CRT_INTERNAL_LOCAL_PRINTF_OPTIONS,
                                        stdout, format, NULL, ap);
  }
  va_end(ap);
  return result;
}

__attribute__((noinline))
static int wide_list(unsigned api, const wchar_t *format, ...)
{
  va_list ap;
  va_start(ap, format);
  int result;
  switch (api) {
    case 5: result = vfwprintf(stdout, format, ap); break;
    case 6: result = vwprintf(format, ap); break;
    default:
      result = __stdio_common_vfwprintf(_CRT_INTERNAL_LOCAL_PRINTF_OPTIONS,
                                         stdout, format, NULL, ap);
  }
  va_end(ap);
  return result;
}

__attribute__((noinline))
static int narrow_item(unsigned api, const char *label, const char *value)
{
  int result;
  switch (api) {
    case 0: result = printf("%s=", label); break;
    case 3: result = fprintf(stdout, "%s=", label); break;
    default: result = narrow_list(api, "%s=", label);
  }
  fputs(value, stdout);
  fputc('\n', stdout);
  return result;
}

__attribute__((noinline))
static int wide_item(unsigned api, const wchar_t *label, const wchar_t *value)
{
  int result;
  switch (api) {
    case 4: result = wprintf(L"%ls=", label); break;
    case 7: result = fwprintf(stdout, L"%ls=", label); break;
    default: result = wide_list(api, L"%ls=", label);
  }
  fputws(value, stdout);
  fputwc(L'\n', stdout);
  return result;
}

__attribute__((noinline))
static int narrow_buffer(unsigned direct, const char *format, ...)
{
  char buffer[80];
  va_list ap;
  va_start(ap, format);
  int result = direct
    ? __stdio_common_vsprintf(_CRT_INTERNAL_LOCAL_PRINTF_OPTIONS
                               | _CRT_INTERNAL_PRINTF_STANDARD_SNPRINTF_BEHAVIOR,
                               buffer, sizeof(buffer), format, NULL, ap)
    : vsnprintf(buffer, sizeof(buffer), format, ap);
  va_end(ap);
  if (result >= 0 && result < (int)sizeof(buffer))
    fwrite(buffer, 1, (size_t)result, stdout);
  return result;
}

__attribute__((noinline))
static int wide_buffer(unsigned direct, const wchar_t *format, ...)
{
  wchar_t buffer[80];
  va_list ap;
  va_start(ap, format);
  int result = direct
    ? __stdio_common_vswprintf(_CRT_INTERNAL_LOCAL_PRINTF_OPTIONS
                                | _CRT_INTERNAL_PRINTF_STANDARD_SNPRINTF_BEHAVIOR,
                                buffer, 80, format, NULL, ap)
    : vswprintf(buffer, 80, format, ap);
  va_end(ap);
  if (result >= 0 && result < 80)
    fputws(buffer, stdout);
  return result;
}

int main(int argc, char **argv)
{
  unsigned which = 100;
  if (argc == 2) {
    which = 0;
    for (const char *p = argv[1]; *p; ++p) {
      if (*p < '0' || *p > '9')
        return 100;
      which = which * 10 + *p - '0';
    }
  }
  struct { WORD machine, reserved; DWORD attributes; } machine = {0, 0, 0};
  unsigned metadata[12] = {0};
  metadata[0] = 0x4D535354;
  metadata[1] = 1;
  metadata[2] = which;
  metadata[3] = sizeof(va_list);
  metadata[4] = ms_stdio_ansi_at_include;
  metadata[5] = GetProcessInformation(GetCurrentProcess(),
      (PROCESS_INFORMATION_CLASS)9, &machine, sizeof(machine));
  metadata[6] = machine.machine;
  if (!metadata[5] || metadata[6] != 0xaa64) {
    write_metadata(metadata, sizeof(metadata));
    return 101;
  }
  int first = 0, second = 0;
  errno = 0;
  if (which <= 3 || which == 8) {
    first = narrow_item(which, "username", "dummy-user");
    metadata[9] = errno;
    errno = 0;
    second = narrow_item(which, "password", "dummy-password");
  } else if (which <= 7 || which == 9) {
    first = wide_item(which, L"username", L"dummy-user");
    metadata[9] = errno;
    errno = 0;
    second = wide_item(which, L"password", L"dummy-password");
  } else if (which == 10 || which == 12) {
    first = narrow_buffer(which == 12, "%d %llu %.1f %s",
                           17, 1234567890123ULL, 4.5, "safe");
  } else if (which == 11 || which == 13) {
    first = wide_buffer(which == 13, L"%d %llu %.1f %ls",
                         17, 1234567890123ULL, 4.5, L"safe");
  } else if (which == 14) {
    first = fputs("username=dummy-user\npassword=dummy-password\n", stdout);
  } else if (which == 15) {
    first = fputws(L"username=dummy-user\npassword=dummy-password\n", stdout);
  } else {
    return 100;
  }
  metadata[7] = (unsigned)first;
  metadata[8] = (unsigned)second;
  metadata[10] = errno;
  metadata[11] = (unsigned)fflush(stdout);
  if (!write_metadata(metadata, sizeof(metadata)))
    return 102;
  return first < 0 || second < 0 || metadata[11] != 0;
}

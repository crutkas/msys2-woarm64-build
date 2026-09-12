#include <windows.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* The builtin need not expose callback changes to ordinary C globals. */
static volatile unsigned process_calls, flush_calls;
static volatile int fail_flush, abort_status;
static const uintptr_t first = UINT64_C(0x10000003d);
static const SIZE_T length = UINT64_C(0x100000005);

static HANDLE WINAPI current_process(void)
{
  ++process_calls;
  return (HANDLE)(intptr_t)-1;
}

static BOOL WINAPI flush_cache(HANDLE process, LPCVOID address, SIZE_T size)
{
  ++flush_calls;
  if (process != (HANDLE)(intptr_t)-1 || (uintptr_t)address != first || size != length)
    ExitProcess(78);
  return !fail_flush;
}

/* Test-only import cells expose the OS boundary without allocating 4 GiB. */
HANDLE (WINAPI *__imp_GetCurrentProcess)(void) = current_process;
BOOL (WINAPI *__imp_FlushInstructionCache)(HANDLE, LPCVOID, SIZE_T) = flush_cache;

static void aborted(int number)
{
  unsigned expected_calls = abort_status == 71 ? 1 : 0;
  ExitProcess(number == SIGABRT && process_calls == expected_calls
              && flush_calls == expected_calls ? (UINT)abort_status : 79);
}

int main(int argc, char **argv)
{
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  process_calls = flush_calls = 0;
  if (argc == 2) {
    if (!strcmp(argv[1], "failure")) {
      fail_flush = 1;
      abort_status = 71;
    } else if (!strcmp(argv[1], "reversed")) {
      abort_status = 72;
    } else {
      return 10;
    }
    if (signal(SIGABRT, aborted) == SIG_ERR)
      return 11;
  }
  __builtin___clear_cache((char *)first, (char *)first);
  __builtin___clear_cache(NULL, NULL);
  if (process_calls || flush_calls)
    return 12;
  __builtin___clear_cache((char *)first,
      (char *)(abort_status == 72 ? first - 1 : first + length));
  if (abort_status || process_calls != 1 || flush_calls != 1)
    return 13;
  puts("cache-contract-ok empty=0 byte-range=4294967301");
  return 0;
}

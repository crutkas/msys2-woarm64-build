#include "ms-varargs-abi.h"

__declspec(dllimport) void *GetCurrentProcess(void);
__declspec(dllimport) int GetProcessInformation(void *, int, void *, unsigned long);
__declspec(dllimport) unsigned short *GetCommandLineW(void);
__declspec(dllimport) void *GetStdHandle(unsigned long);
__declspec(dllimport) int WriteFile(void *, const void *, unsigned long,
                                  unsigned long *, void *);
__declspec(dllimport) __attribute__((noreturn)) void ExitProcess(unsigned);

volatile ms_u64 ms_seen[4];

struct ms_record {
  unsigned magic, version, which, result, producer_va_size, consumer_va_size;
  unsigned machine_query, machine;
  ms_u64 observed[4];
};

void ms_varargs_entry(void)
{
  const unsigned short *command = GetCommandLineW();
  const unsigned short *last = command;
  for (const unsigned short *p = command; *p; ++p)
    if (*p == ' ')
      last = p + 1;
  unsigned which = 0;
  while (*last >= '0' && *last <= '9')
    which = which * 10 + *last++ - '0';
  struct { unsigned short machine, reserved; unsigned attributes; } machine;
  machine.machine = machine.reserved = 0;
  machine.attributes = 0;
  struct ms_record record;
  record.magic = 0x4D535641;
  record.version = 1;
  record.which = which;
  record.producer_va_size = ms_producer_va_size();
  record.consumer_va_size = ms_consumer_va_size();
  record.machine_query = GetProcessInformation(GetCurrentProcess(), 9,
                                                &machine, sizeof(machine));
  record.machine = machine.machine;
  record.result = record.machine_query && record.machine == 0xaa64
                  ? ms_run_case(which) : 101;
  for (unsigned i = 0; i != 4; ++i)
    record.observed[i] = ms_seen[i];
  unsigned long written = 0;
  int ok = WriteFile(GetStdHandle((unsigned long)-11), &record, sizeof(record),
                     &written, (void *)0);
  ExitProcess(ok && written == sizeof(record) ? record.result : 102);
}

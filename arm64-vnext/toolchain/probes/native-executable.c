#include <windows.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

#if defined(__CYGWIN__) && !defined(__MSYS__)
#error MSYS application profile is required for the Cygwin target
#endif

static __thread int local_value = 7;

static void *worker(void *main_local)
{
  if (&local_value == main_local || local_value != 7)
    return 0;
  local_value = 42;
  return (void *)(uintptr_t)local_value;
}

int main(void)
{
  struct {
    WORD machine;
    WORD reserved;
    DWORD attributes;
  } machine = { 0, 0, 0 };
  if (!GetProcessInformation(GetCurrentProcess(), (PROCESS_INFORMATION_CLASS)9,
                             &machine, sizeof(machine)) || machine.machine != 0xaa64)
    return 10;
  pthread_t thread;
  void *answer = 0;
  if (pthread_create(&thread, 0, worker, &local_value) != 0 ||
      pthread_join(thread, &answer) != 0)
    return 11;
  if ((uintptr_t)answer != 42 || local_value != 7)
    return 12;
  puts("native-executable-ok");
  return 0;
}

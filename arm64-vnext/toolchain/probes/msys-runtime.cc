#include <windows.h>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <mutex>
#include <stdexcept>
#include <thread>

#ifndef __MSYS__
#error The compiler must select its MSYS application profile by default
#endif
static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS ARM64 LP64");
static thread_local int local_value = 7;

int main()
{
  struct {
    WORD machine;
    WORD reserved;
    DWORD attributes;
  } machine = {};
  if (!GetProcessInformation(GetCurrentProcess(),
                             static_cast<PROCESS_INFORMATION_CLASS>(9),
                             &machine, sizeof(machine)) || machine.machine != 0xaa64)
    return 10;
  char text[80];
  std::snprintf(text, sizeof(text), "%ld %.1f %s", 123456789012345L, 3.5, "msys");
  if (std::strcmp(text, "123456789012345 3.5 msys"))
    return 11;
  std::mutex mutex;
  int result = 0;
  int *main_local = &local_value;
  std::thread worker([&] {
    std::lock_guard<std::mutex> guard(mutex);
    if (&local_value == main_local || local_value != 7)
      return;
    local_value = 41;
    try {
      throw std::runtime_error("MSYS exception");
    } catch (const std::runtime_error &error) {
      if (!std::strcmp(error.what(), "MSYS exception"))
        result = local_value + 1;
    }
  });
  worker.join();
  if (result != 42 || local_value != 7)
    return 12;
  if ((std::filesystem::path("a") / "b").filename() != "b")
    return 13;
  std::puts("native-msys-runtime-ok");
  return 0;
}

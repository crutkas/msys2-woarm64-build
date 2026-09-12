#include <windows.h>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <thread>
#include <vector>

static_assert(sizeof(void *) == 8 && sizeof(long) == 4, "Windows ARM64 LLP64");

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
  char buffer[80];
  std::snprintf(buffer, sizeof(buffer), "%d %llu %.1f %s",
                -17, 123456789012345ULL, 3.5, "arm64");
  if (std::strcmp(buffer, "-17 123456789012345 3.5 arm64") != 0)
    return 11;
  std::vector<int> values{1, 2, 3, 4};
  std::mutex mutex;
  int sum = 0;
  std::thread worker([&] {
    std::lock_guard<std::mutex> lock(mutex);
    sum = std::accumulate(values.begin(), values.end(), 0);
  });
  worker.join();
  if (sum != 10)
    return 12;
  bool caught = false;
  try {
    throw std::runtime_error("arm64 exception");
  } catch (const std::runtime_error &error) {
    caught = std::strcmp(error.what(), "arm64 exception") == 0;
  }
  if (!caught)
    return 13;
  if ((std::filesystem::path("a") / "b").filename() != "b")
    return 14;
  std::puts("native-runtime-ok");
  return 0;
}

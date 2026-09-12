#include <new>
#include <type_traits>

static_assert(sizeof(void *) == 8, "ARM64 pointers");
static_assert(sizeof(long) == 8, "Cygwin LP64 ABI");
static_assert(sizeof(long double) == 8, "Cygwin ARM64 long double ABI");
static_assert(std::is_same<decltype(sizeof(0)), unsigned long>::value,
              "Cygwin size_t ABI");

int *placement_new_probe(void *storage)
{
  return new (storage) int(73);
}

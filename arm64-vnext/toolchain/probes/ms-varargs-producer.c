#include "ms-varargs-abi.h"

unsigned ms_producer_va_size(void) { return sizeof(ms_va_list); }

static int forward_copy(int tag, ...)
{
  ms_va_list ap, copied;
  __builtin_va_start(ap, tag);
  __builtin_va_copy(copied, ap);
  int first = __builtin_va_arg(copied, int);
  __builtin_va_end(copied);
  int result = ms_list_bridge(ap);
  __builtin_va_end(ap);
  return first != 17 || result;
}

int ms_run_case(unsigned which)
{
  struct ms_pair pair = {7, 8};
  struct ms_hfa hfa = {1.25, 2.5, 5.0};
  struct ms_aligned aligned = {0x1122334455667788ULL, 0x8877665544332211ULL};
  ms_u64 tail = 0x123456789ABCDEF0ULL;
  ms_u128 wide = ((ms_u128)aligned.b << 64) | aligned.a;
  switch (which) {
    case 0: return sizeof(ms_va_list) != 8 || ms_consumer_va_size() != 8;
    case 1: return ms_mixed(0, 17, 1234567890123ULL, 4.5, "safe");
    case 2: return ms_named_double(4.5, 17, 6.5);
    case 3: return ms_fixed_double_hfa(3.25, hfa) != 12.0;
    case 4: {
      struct ms_hfa result = ms_fixed_hfa_return(2.5);
      return result.a != 2.5 || result.b != 3.5 || result.c != 4.5;
    }
    case 5: return ms_variadic_return(0, 4.5) != 5.5;
    case 6: return ms_pair_split(0, 1ULL, 2ULL, 3ULL, 4ULL, 5ULL, 6ULL, pair, 9ULL);
    case 7: return ms_large_hfa(0, hfa, 17);
    case 8: return forward_copy(0, 17, 1234567890123ULL, 4.5);
    case 9: return ms_stack(0, 1ULL, 2ULL, 3ULL, 4ULL, 5ULL, 6ULL,
                            7ULL, 8ULL, 9ULL, 10ULL, 11ULL, 12ULL);
    case 10: return ms_eight_named(0, 1, 2, 3, 4, 5, 6, 7, 123ULL, 4.5);
    case 11: return ms_nine_named(0, 1, 2, 3, 4, 5, 6, 7, 8, 123ULL, 4.5);
    case 12: return ms_named_pair(0, 1, 2, 3, 4, 5, 6, pair, 9ULL);
    case 13: return ms_aligned_register(17, aligned, tail);
    case 14: return ms_aligned_stack(17, 1ULL, 2ULL, 3ULL, 4ULL, 5ULL,
                                     6ULL, 7ULL, 8ULL, aligned, tail);
    case 15: return ms_int128_register(17, wide, tail);
    case 16: return ms_int128_stack(17, 1ULL, 2ULL, 3ULL, 4ULL, 5ULL,
                                    6ULL, 7ULL, 8ULL, wide, tail);
    case 17: return ms_aligned_named(17, aligned, tail);
    default: return 100;
  }
}

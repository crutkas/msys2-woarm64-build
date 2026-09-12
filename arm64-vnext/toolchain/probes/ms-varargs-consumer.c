#include "ms-varargs-abi.h"

#define START(ap, last) ms_va_list ap; __builtin_va_start(ap, last)
#define ARG(ap, type) __builtin_va_arg(ap, type)
#define END(ap) __builtin_va_end(ap)

unsigned ms_consumer_va_size(void) { return sizeof(ms_va_list); }

int ms_mixed(int tag, ...)
{
  START(ap, tag);
  int i = ARG(ap, int);
  ms_u64 u = ARG(ap, ms_u64);
  double d = ARG(ap, double);
  const char *s = ARG(ap, const char *);
  END(ap);
  ms_seen[0] = i;
  ms_seen[1] = u;
  return !(i == 17 && u == 1234567890123ULL && d == 4.5
           && s[0] == 's' && s[1] == 'a' && s[2] == 'f'
           && s[3] == 'e' && s[4] == 0);
}

int ms_named_double(double named, ...)
{
  START(ap, named);
  int i = ARG(ap, int);
  double d = ARG(ap, double);
  END(ap);
  ms_seen[0] = i;
  return !(named == 4.5 && i == 17 && d == 6.5);
}

double ms_fixed_double_hfa(double d, struct ms_hfa h)
{
  return d + h.a + h.b + h.c;
}

struct ms_hfa ms_fixed_hfa_return(double d)
{
  struct ms_hfa result = {d, d + 1.0, d + 2.0};
  return result;
}

double ms_variadic_return(int tag, ...)
{
  START(ap, tag);
  double result = ARG(ap, double);
  END(ap);
  return result + 1.0;
}

int ms_pair_split(int tag, ...)
{
  START(ap, tag);
  int bad = 0;
  for (ms_u64 i = 1; i <= 6; ++i)
    bad |= ARG(ap, ms_u64) != i;
  struct ms_pair p = ARG(ap, struct ms_pair);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  ms_seen[0] = p.a;
  ms_seen[1] = p.b;
  ms_seen[2] = tail;
  return bad || p.a != 7 || p.b != 8 || tail != 9;
}

int ms_large_hfa(int tag, ...)
{
  START(ap, tag);
  struct ms_hfa h = ARG(ap, struct ms_hfa);
  int tail = ARG(ap, int);
  END(ap);
  ms_seen[0] = tail;
  return !(h.a == 1.25 && h.b == 2.5 && h.c == 5.0 && tail == 17);
}

int ms_list_bridge(ms_va_list incoming)
{
  ms_va_list copied;
  __builtin_va_copy(copied, incoming);
  int i = ARG(incoming, int);
  ms_u64 u = ARG(incoming, ms_u64);
  double d = ARG(incoming, double);
  int first_again = ARG(copied, int);
  END(copied);
  ms_seen[0] = i;
  ms_seen[1] = u;
  ms_seen[2] = first_again;
  return !(i == 17 && u == 1234567890123ULL && d == 4.5 && first_again == 17);
}

int ms_stack(int tag, ...)
{
  START(ap, tag);
  int bad = 0;
  for (ms_u64 i = 1; i <= 12; ++i) {
    ms_u64 actual = ARG(ap, ms_u64);
    bad |= actual != i;
    if (i >= 9)
      ms_seen[i - 9] = actual;
  }
  END(ap);
  return bad;
}

int ms_eight_named(int a, int b, int c, int d, int e, int f, int g, int h, ...)
{
  START(ap, h);
  ms_u64 u = ARG(ap, ms_u64);
  double value = ARG(ap, double);
  END(ap);
  ms_seen[0] = u;
  return !(a + b + c + d + e + f + g + h == 28 && u == 123 && value == 4.5);
}

int ms_nine_named(int a, int b, int c, int d, int e, int f, int g, int h,
                  int i, ...)
{
  START(ap, i);
  ms_u64 u = ARG(ap, ms_u64);
  double value = ARG(ap, double);
  END(ap);
  ms_seen[0] = u;
  return !(a + b + c + d + e + f + g + h + i == 36
           && u == 123 && value == 4.5);
}

int ms_named_pair(ms_u64 a, ms_u64 b, ms_u64 c, ms_u64 d, ms_u64 e,
                  ms_u64 f, ms_u64 g, struct ms_pair pair, ...)
{
  START(ap, pair);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  ms_seen[0] = pair.a;
  ms_seen[1] = pair.b;
  ms_seen[2] = tail;
  return !(a + b + c + d + e + f + g == 21
           && pair.a == 7 && pair.b == 8 && tail == 9);
}

static int aligned_values(struct ms_aligned a, ms_u64 tail)
{
  ms_seen[0] = a.a;
  ms_seen[1] = a.b;
  ms_seen[2] = tail;
  return a.a != 0x1122334455667788ULL || a.b != 0x8877665544332211ULL
         || tail != 0x123456789ABCDEF0ULL;
}

int ms_aligned_register(int tag, ...)
{
  START(ap, tag);
  struct ms_aligned a = ARG(ap, struct ms_aligned);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  return aligned_values(a, tail);
}

int ms_aligned_stack(int tag, ...)
{
  START(ap, tag);
  int bad = 0;
  for (ms_u64 i = 1; i <= 8; ++i)
    bad |= ARG(ap, ms_u64) != i;
  struct ms_aligned a = ARG(ap, struct ms_aligned);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  int values = aligned_values(a, tail);
  return bad || values;
}

static int int128_values(ms_u128 value, ms_u64 tail)
{
  struct ms_aligned words = {(ms_u64)value, (ms_u64)(value >> 64)};
  return aligned_values(words, tail);
}

int ms_int128_register(int tag, ...)
{
  START(ap, tag);
  ms_u128 value = ARG(ap, ms_u128);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  return int128_values(value, tail);
}

int ms_int128_stack(int tag, ...)
{
  START(ap, tag);
  int bad = 0;
  for (ms_u64 i = 1; i <= 8; ++i)
    bad |= ARG(ap, ms_u64) != i;
  ms_u128 value = ARG(ap, ms_u128);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  int values = int128_values(value, tail);
  return bad || values;
}

int ms_aligned_named(int tag, struct ms_aligned named, ...)
{
  START(ap, named);
  ms_u64 tail = ARG(ap, ms_u64);
  END(ap);
  return tag != 17 || aligned_values(named, tail);
}

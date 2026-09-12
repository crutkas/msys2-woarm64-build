#include <stdarg.h>

extern long called_function(long);

long unwind_example(long value)
{
  return called_function(value) + value;
}

long unwind_varargs(long count, ...)
{
  va_list args;
  va_start(args, count);
  long value = 0;
  for (long i = 0; i < count; ++i)
    value += va_arg(args, long);
  va_end(args);
  return called_function(value) + value;
}

long unwind_conditional(long *value)
{
  if (!value)
    return 0;
  long result = called_function(*value);
  if (result)
    __asm__ __volatile__ ("" ::: "x19", "x20", "x21", "x22", "x23",
                         "x24", "x25", "x26", "x27", "x28");
  return result;
}

#include "compiler-large-frame.c"

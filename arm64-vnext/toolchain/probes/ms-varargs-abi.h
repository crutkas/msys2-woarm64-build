#ifndef MS_VARARGS_ABI_H
#define MS_VARARGS_ABI_H

typedef __builtin_va_list ms_va_list;
typedef unsigned long long ms_u64;
typedef unsigned __int128 ms_u128;

#ifdef __cplusplus
template<class T> struct ms_char_pointer { enum { value = 0 }; };
template<> struct ms_char_pointer<char *> { enum { value = 1 }; };
static_assert(ms_char_pointer<ms_va_list>::value, "MS va_list must be char*");
#else
_Static_assert(__builtin_types_compatible_p(ms_va_list, char *),
               "MS va_list must be char*");
#endif

struct ms_pair { ms_u64 a, b; };
struct ms_hfa { double a, b, c; };
struct __attribute__((aligned(16))) ms_aligned { ms_u64 a, b; };

#ifdef __cplusplus
extern "C" {
#endif

extern volatile ms_u64 ms_seen[4];
unsigned ms_producer_va_size(void);
unsigned ms_consumer_va_size(void);
int ms_mixed(int, ...);
int ms_named_double(double, ...);
double ms_fixed_double_hfa(double, struct ms_hfa);
struct ms_hfa ms_fixed_hfa_return(double);
double ms_variadic_return(int, ...);
int ms_pair_split(int, ...);
int ms_large_hfa(int, ...);
int ms_list_bridge(ms_va_list);
int ms_stack(int, ...);
int ms_eight_named(int, int, int, int, int, int, int, int, ...);
int ms_nine_named(int, int, int, int, int, int, int, int, int, ...);
int ms_named_pair(ms_u64, ms_u64, ms_u64, ms_u64, ms_u64, ms_u64,
                  ms_u64, struct ms_pair, ...);
int ms_aligned_register(int, ...);
int ms_aligned_stack(int, ...);
int ms_int128_register(int, ...);
int ms_int128_stack(int, ...);
int ms_aligned_named(int, struct ms_aligned, ...);
int ms_run_case(unsigned);

#ifdef __cplusplus
}
#endif
#endif

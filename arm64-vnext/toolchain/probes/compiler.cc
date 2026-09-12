extern "C" unsigned long long c_calculate(unsigned long long);
extern "C" int native_machine(void);
extern "C" unsigned long long libgcc_calculate(unsigned long long,
                                             unsigned long long,
                                             unsigned long long);
extern "C" __declspec(dllimport) void ExitProcess(unsigned int);

template<unsigned long long N> struct Calculator {
  static unsigned long long calculate(unsigned long long value)
  {
    return c_calculate(value) ^ N;
  }
};

extern "C" void ProbeEntry(void)
{
  volatile unsigned long long input = 1234567;
  unsigned long long expected = (1234567ULL * 17 + 9) ^ 0x12345678ULL;
#ifdef PROBE_NEGATIVE_CONTROL
  expected ^= 1;
#endif
  bool valid = Calculator<0x12345678ULL>::calculate(input) == expected;
  valid = valid && libgcc_calculate(1, 7, 3) == 6148914691236517207ULL;
  ExitProcess(valid && native_machine() ? 73 : 91);
}

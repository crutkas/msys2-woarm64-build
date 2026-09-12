/* No CRT or MSYS runtime is available at this bootstrap stage.
   Declare only the Windows ABI needed to exercise the compiler and loader. */
__declspec(dllimport) void *GetCurrentProcess(void);
__declspec(dllimport) int GetProcessInformation(void *, int, void *, unsigned int);
__declspec(dllimport) void ExitProcess(unsigned int);

struct machine_information {
  unsigned short machine;
  unsigned short reserved;
  unsigned int attributes;
};

unsigned long long c_calculate(unsigned long long x)
{
  return x * 17 + 9;
}

unsigned long long libgcc_calculate(unsigned long long high,
                                  unsigned long long low,
                                  unsigned long long divisor)
{
  return (((unsigned __int128)high << 64) | low) / divisor;
}

int native_machine(void)
{
  struct machine_information info = { 0, 0, 0 };
  if (!GetProcessInformation(GetCurrentProcess(), 9, &info, sizeof(info)))
    return 0;
  return info.machine == 0xaa64;
}

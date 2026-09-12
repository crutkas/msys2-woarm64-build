#include <string>

static std::string message = "MSYS module constructors";

extern "C" __declspec(dllexport) int msys_module_answer()
{
  return message == "MSYS module constructors" ? 42 : -1;
}

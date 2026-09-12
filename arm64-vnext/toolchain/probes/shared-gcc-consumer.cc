#include <windows.h>
#include <clocale>
#include <cmath>
#include <complex>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <locale>
#include <sstream>
#include <stdexcept>

extern "C" __declspec(dllimport) void provider_throw();
extern "C" __declspec(dllimport) int provider_thread_tls();
extern "C" __declspec(dllimport) void provider_rethrow(void (*)());
extern "C" __declspec(dllimport) std::exception_ptr provider_capture(void (*)());

struct ConsumerError : std::runtime_error {
    ConsumerError() : std::runtime_error("consumer exception") {}
};
static int cleanups;
static void consumer_throw()
{
    struct Guard {
        ~Guard() { ++cleanups; }
    } guard;
    throw ConsumerError();
}

int main(int argc, char **argv)
{
    struct {
        WORD machine;
        WORD reserved;
        DWORD attributes;
    } machine = {};
    if (!GetProcessInformation(GetCurrentProcess(), static_cast<PROCESS_INFORMATION_CLASS>(9),
                               &machine, sizeof(machine)) || machine.machine != 0xaa64)
        return 10;
    static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS LP64 required");
    int caught = 0;
    try {
        provider_throw();
    } catch (const std::runtime_error &error) {
        caught = std::strcmp(error.what(), "shared exception") == 0;
    }
    if (!caught || provider_thread_tls() != 42)
        return 11;
    int crossed_back = 0;
    try {
        provider_rethrow(consumer_throw);
    } catch (const ConsumerError &error) {
        crossed_back = std::strcmp(error.what(), "consumer exception") == 0;
    }
    if (!crossed_back || cleanups != 1)
        return 18;
    auto pending = provider_capture(consumer_throw);
    if (!pending || cleanups != 2)
        return 19;
    crossed_back = 0;
    try {
        std::rethrow_exception(pending);
    } catch (const ConsumerError &error) {
        crossed_back = std::strcmp(error.what(), "consumer exception") == 0;
    }
    if (!crossed_back)
        return 20;
    double integral = 0;
    const std::complex<double> z(1.25, 0.5);
    if (std::modf(4.25, &integral) != 0.25 || integral != 4.0 ||
        std::abs(std::exp(std::log(z)) - z) > 1e-12)
        return 21;
    if (!std::setlocale(LC_ALL, "C.UTF-8"))
        return 12;
    // Match this pinned target's generic libstdc++ locale backend: named
    // non-C facets are unsupported, independently of the C runtime locale.
    std::locale current("C");
    try {
        std::locale unsupported("C.UTF-8");
        return 17;
    } catch (const std::runtime_error &) {
    }
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << 123456789012345L << ' ' << 3.5;
    if (stream.str() != "123456789012345 3.5")
        return 13;
    const auto &ctype = std::use_facet<std::ctype<char>>(current);
    if (!ctype.is(std::ctype_base::alpha, 'Z') || ctype.toupper('a') != 'A')
        return 14;
    if ((std::filesystem::path("native") / "runtime").filename() != "runtime")
        return 15;
    {
        const std::filesystem::path file("shared-runtime-file.txt");
        std::ofstream output(file);
        output << "native shared filesystem";
        output.close();
        if (std::filesystem::file_size(file) != 24 ||
            !std::filesystem::is_regular_file(file) || !std::filesystem::remove(file))
            return 16;
    }
    std::cout << "native-msys-shared-gcc-cpp-ok" << std::endl;
    if (argc == 2 && std::strcmp(argv[1], "--hold") == 0)
        Sleep(1500);
    return 0;
}

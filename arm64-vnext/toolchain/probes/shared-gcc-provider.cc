#include <atomic>
#include <stdexcept>
#include <string>
#include <thread>

static std::atomic<int> thread_destructors{0};
static std::atomic<int> exception_destructors{0};
struct State {
    int value = 17;
    ~State() { thread_destructors.fetch_add(1, std::memory_order_relaxed); }
};
static thread_local State state;
static std::string startup = "shared C++ constructor";

extern "C" __declspec(dllexport) void provider_rethrow(void (*callback)())
{
    try {
        callback();
    } catch (const std::exception &) {
        throw;
    }
}

extern "C" __declspec(dllexport) std::exception_ptr provider_capture(void (*callback)())
{
    try {
        callback();
    } catch (...) {
        return std::current_exception();
    }
    return {};
}

extern "C" __declspec(dllexport) void provider_throw()
{
    struct Guard {
        ~Guard() { exception_destructors.fetch_add(1, std::memory_order_relaxed); }
    } guard;
    throw std::runtime_error("shared exception");
}

extern "C" __declspec(dllexport) int provider_thread_tls()
{
    int result = 0;
    std::thread worker([&] {
        if (state.value != 17)
            return;
        state.value = 39;
        try {
            provider_throw();
        } catch (const std::runtime_error &error) {
            if (std::string(error.what()) == "shared exception")
                result = state.value + 3;
        }
    });
    worker.join();
    return result == 42 && state.value == 17 && startup == "shared C++ constructor" &&
           thread_destructors.load() == 1 && exception_destructors.load() == 2 ? 42 : -1;
}

#include <windows.h>
#include <cstdio>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <sys/wait.h>
#include <unistd.h>

static int trace;
static int nested_catches;

struct Guard {
    int id;
    ~Guard() { trace = trace * 10 + id; }
};

struct DbException : std::runtime_error {
    DbException() : std::runtime_error("controlled-db-error") {}
};

struct NestedGuard {
    ~NestedGuard() {
        try {
            throw std::logic_error("nested");
        } catch (const std::logic_error &) {
            ++nested_catches;
        }
        trace = trace * 10 + 2;
    }
};

__attribute__((noinline)) static void leaf()
{
    Guard guard{3};
    throw DbException();
}

__attribute__((noinline)) static void middle()
{
    Guard guard{2};
    leaf();
}

static int exercise(const char *name)
{
    if (!std::strcmp(name, "plain")) {
        try {
            Guard guard{1};
            throw DbException();
        } catch (const std::runtime_error &error) {
            return trace == 1 && !std::strcmp(error.what(), "controlled-db-error") ? 0 : 61;
        }
    } else if (!std::strcmp(name, "cleanup")) {
        try {
            Guard guard{1};
            middle();
        } catch (const DbException &) {
            return trace == 321 ? 0 : 62;
        }
    } else if (!std::strcmp(name, "rethrow")) {
        try {
            Guard outer{1};
            try {
                Guard inner{2};
                throw DbException();
            } catch (const DbException &) {
                if (trace != 2)
                    return 63;
                throw;
            }
        } catch (const std::runtime_error &error) {
            return trace == 21 && !std::strcmp(error.what(), "controlled-db-error") ? 0 : 64;
        }
    } else if (!std::strcmp(name, "nested")) {
        try {
            Guard outer{1};
            NestedGuard inner;
            throw DbException();
        } catch (const DbException &) {
            return trace == 21 && nested_catches == 1 ? 0 : 65;
        }
    } else if (!std::strcmp(name, "exception-ptr")) {
        std::exception_ptr saved;
        try {
            Guard inner{2};
            throw DbException();
        } catch (...) {
            saved = std::current_exception();
        }
        try {
            Guard outer{1};
            std::rethrow_exception(saved);
        } catch (const DbException &) {
            return trace == 21 ? 0 : 66;
        }
    } else if (!std::strcmp(name, "uncaught")) {
        std::set_terminate([] { ExitProcess(73); });
        throw DbException();
    } else if (!std::strcmp(name, "winapi-256")) {
        ExitProcess(256);
    } else if (!std::strcmp(name, "crash")) {
        RaiseException(0xC0000005, EXCEPTION_NONCONTINUABLE, 0, NULL);
    }
    return 67;
}

int main(int argc, char **argv)
{
    if (argc < 2)
        return 68;
    if (argc == 3 && !std::strcmp(argv[2], "fork")) {
        pid_t child = fork();
        if (child < 0)
            return 69;
        if (child) {
            int status;
            if (waitpid(child, &status, 0) != child || !WIFEXITED(status))
                return 70;
            return WEXITSTATUS(status);
        }
    }
    int result = exercise(argv[1]);
    std::printf("case=%s trace=%d nested=%d result=%d\n", argv[1], trace, nested_catches, result);
    return result;
}

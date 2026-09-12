#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <sys/wait.h>
#include <unistd.h>

class DbException : public std::runtime_error {
public:
    DbException() : std::runtime_error("owned controlled exception") {}
};

static int exercise()
{
    int unwound = 0;
    struct Guard {
        int &count;
        ~Guard() { ++count; }
    };
    try {
        Guard guard{unwound};
        throw DbException();
    } catch (const DbException &error) {
        if (unwound != 1 || std::strcmp(error.what(), "owned controlled exception"))
            return 71;
        std::puts("caught DbException with exactly one destructor");
        return 0;
    }
    return 72;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !std::strcmp(argv[1], "fork")) {
        pid_t child = fork();
        if (child < 0)
            return 73;
        if (child == 0)
            return exercise();
        int status;
        if (waitpid(child, &status, 0) != child || !WIFEXITED(status))
            return 74;
        return WEXITSTATUS(status);
    }
    return exercise();
}

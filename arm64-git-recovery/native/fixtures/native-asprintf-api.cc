#include <autosprintf.h>
#include <clocale>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <string>
#include <ctime>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2 || sizeof(void *) != 8 || sizeof(long) != 8 || !std::setlocale(LC_ALL, "C.UTF-8"))
        return 2;
    FILE *ready = std::fopen("ready", "wb");
    if (!ready || std::fclose(ready) != 0)
        return 3;
    std::time_t end = std::time(nullptr) + 30;
    while (access("continue", F_OK) != 0 && std::time(nullptr) < end)
        usleep(50000);
    if (access("continue", F_OK) != 0)
        return 4;
    {
        gnu::autosprintf formatted("%s %d %.1f", "native", 37, 1.5);
        std::string text = formatted;
        gnu::autosprintf copied(formatted);
        gnu::autosprintf assigned("%s", "initial");
        assigned = copied;
        std::ostringstream stream;
        stream << assigned;
        if (text != "native 37 1.5" || stream.str() != text)
            return 5;
    }
    FILE *report = std::fopen(argv[1], "wb");
    if (!report)
        return 6;
    int written = std::fprintf(report,
        "{\"passed\":true,\"lp64\":true,\"varargs\":true,\"copy_assign_stream_lifetime\":true}\n");
    if (std::fclose(report) != 0 || written < 0)
        return 7;
    return 0;
}

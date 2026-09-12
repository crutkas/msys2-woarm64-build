#include <cursesw.h>
#include <clocale>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv)
{
    if (argc != 2 || !std::setlocale(LC_ALL, "C.UTF-8"))
        return 2;
    NCursesWindow window(4, 40, 0, 0);
    char text[64] = {};
    const char expected[] = "native-cpp 37 1.5";
    bool passed = window.height() == 4 && window.width() == 40;
    passed = passed && window.printw(0, 0, "native-cpp %d %.1f", 37, 1.5) != ERR;
    passed = passed && window.instr(0, 0, text, sizeof(expected) - 1) == sizeof(expected) - 1;
    passed = passed && std::strcmp(text, expected) == 0;
    FILE *report = std::fopen(argv[1], "wb");
    if (!report)
        return 3;
    std::fprintf(report, "{\"passed\":%s,\"height\":%d,\"width\":%d,\"text\":\"%s\"}\n",
                 passed ? "true" : "false", window.height(), window.width(), text);
    if (std::fclose(report) != 0)
        return 4;
    window.addstr(1, 0, "curses-cpp-ready");
    window.refresh();
    int input = window.getch();
    return passed && (input == '\n' || input == '\r') ? 0 : 5;
}

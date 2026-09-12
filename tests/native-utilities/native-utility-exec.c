#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: native-utility-exec PROGRAM [ARG...]\n");
        return 2;
    }
    execv(argv[1], argv + 1);
    perror("native utility execv");
    return 127;
}

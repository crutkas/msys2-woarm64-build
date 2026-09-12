#include <stdio.h>

int main(int argc, char **argv)
{
    FILE *input;
    int value;
    if (argc != 2)
        return 2;
    input = fopen(argv[1], "rb");
    if (input == NULL)
        return 1;
    value = fgetc(input);
    if (fclose(input) != 0 || value != 'R')
        return 3;
    puts("argument-file-ok");
    return 0;
}

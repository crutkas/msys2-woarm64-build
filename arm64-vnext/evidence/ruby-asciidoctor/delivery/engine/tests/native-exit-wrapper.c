#include <process.h>

int main(int argc, char **argv)
{
    if (argc < 2)
        return 2;
    return (int)_spawnv(_P_WAIT, argv[1], (const char *const *)&argv[1]);
}

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

_Static_assert(sizeof(long) == 8, "MSYS LP64 required");
_Static_assert(sizeof(struct termios) > 0, "Complete termios definition required");

int main(void)
{
    struct termios value;
    errno = 0;
    if (tcgetattr(-1, &value) != -1 || errno != EBADF) {
        fprintf(stderr, "Unexpected tcgetattr invalid-fd result: errno=%d\n", errno);
        return 1;
    }
    printf("termios available: size=%zu long=%zu tcgetattr_errno=%d\n",
           sizeof(value), sizeof(long), errno);
    return 0;
}

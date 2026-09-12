#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

_Static_assert(sizeof(long) == 8, "MSYS LP64 is required");

int main(void) {
    int exists = access("/bin/sh", X_OK);
    int path_error = errno;
    printf("bin-sh-access=%d errno=%d\n", exists, exists ? path_error : 0);
    errno = 0;
    FILE *pipe = popen("printf 'native-sqlite-pipe\\n'", "r");
    if (!pipe) {
        fprintf(stderr, "popen failed errno=%d: %s\n", errno, strerror(errno));
        return 1;
    }
    char text[128] = {0};
    size_t count = fread(text, 1, sizeof(text) - 1, pipe);
    int status = pclose(pipe);
    printf("popen-bytes=%zu status=%d text=%s", count, status, text);
    return status == -1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
        strcmp(text, "native-sqlite-pipe\n") != 0;
}

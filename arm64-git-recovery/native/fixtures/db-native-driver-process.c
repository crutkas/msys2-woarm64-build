#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "Native MSYS LP64 required");

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "native driver assertion failed at %d: %s (errno %d)\n", __LINE__, #expr, errno); return 1; \
} } while (0)

int main(int argc, char **argv)
{
    struct stat info;
    pid_t child;
    int status;
    if (argc == 2 && strcmp(argv[1], "child") == 0) {
        puts("DB native fork-exec child PASS");
        return 0;
    }
    CHECK(argc == 1);
    CHECK(access("/bin/sh", X_OK) == 0);
    CHECK(access("/usr/bin/rm", X_OK) == 0);
    CHECK(access("/usr/bin/mkdir", X_OK) == 0);
    CHECK(stat("/tmp", &info) == 0 && S_ISDIR(info.st_mode));
    CHECK(system("mkdir TESTDIR") == 0);
    CHECK(stat("TESTDIR", &info) == 0 && S_ISDIR(info.st_mode));
    CHECK(system("/bin/sh -c 'printf native-shell > TESTDIR/proof'") == 0);
    CHECK(stat("TESTDIR/proof", &info) == 0 && info.st_size == 12);
    CHECK((child = fork()) >= 0);
    if (child == 0) {
        execl(argv[0], argv[0], "child", (char *)NULL);
        perror("native child exec");
        _exit(2);
    }
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(system("rm -rf TESTDIR") == 0);
    CHECK(stat("TESTDIR", &info) == -1 && errno == ENOENT);
    puts("DB native driver PASS: LP64 /bin/sh /tmp mkdir rm system fork exec wait");
    return 0;
}

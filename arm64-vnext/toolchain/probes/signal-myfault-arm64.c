#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/utsname.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    (void)argv;
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size < (long)sizeof(struct utsname))
        return 1;
    void *unreadable = mmap(NULL, page_size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (unreadable == MAP_FAILED)
        return 2;
    for (int iteration = 0; iteration < 8; ++iteration) {
        errno = 0;
        int result = uname(unreadable);
        if (result != -1 || errno != EFAULT) {
            fprintf(stderr, "uname protected page: result=%d errno=%d\n", result, errno);
            return 3;
        }
    }
    if (munmap(unreadable, page_size))
        return 4;
    puts("arm64-myfault-efault-ok: 8 protected-page faults");
    fflush(stdout);
    if (argc > 1)
        usleep(1500000);
    return 0;
}

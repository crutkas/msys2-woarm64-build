#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
#include <dlfcn.h>

static void measure(const char *name, int value, int saved_errno)
{
    printf("%s result=%d errno=%d\n", name, value, value < 0 ? saved_errno : 0);
}

int main(void)
{
    printf("uid=%lu euid=%lu gid=%lu\n",
           (unsigned long)getuid(), (unsigned long)geteuid(), (unsigned long)getgid());
#ifdef RTLD_NEXT
    puts("RTLD_NEXT=defined");
#else
    puts("RTLD_NEXT=absent");
#endif
    if (mkdir("api-dir", 0700) || mkdir("api-no-x", 0700))
        return 90;
    int fd = open("api-dir/file", O_CREAT | O_WRONLY, 0600);
    if (fd < 0 || close(fd))
        return 91;
    fd = open("api-no-x/file", O_CREAT | O_WRONLY, 0600);
    if (fd < 0 || close(fd))
        return 92;
    if (chmod("api-dir", 0500) || chmod("api-no-x", 0600))
        return 93;
    struct stat status;
    if (stat("api-dir", &status))
        return 94;
    printf("parent-mode=%03lo\n", (unsigned long)(status.st_mode & 0777));
    errno = 0;
    int result = access("api-dir", W_OK);
    measure("access-parent-W_OK", result, errno);
    errno = 0;
    result = unlinkat(AT_FDCWD, "api-dir/file", 0);
    measure("unlinkat-child", result, errno);
    errno = 0;
    fd = open("api-no-x/file", O_RDONLY);
    measure("open-through-unsearchable-parent", fd, errno);
    if (fd >= 0)
        close(fd);
    errno = 0;
    result = chdir("api-no-x");
    measure("chdir-unsearchable-parent", result, errno);
    return 0;
}

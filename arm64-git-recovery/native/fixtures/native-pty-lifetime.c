#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pty.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

_Static_assert(sizeof(long) == 8, "Native MSYS LP64 required");

static int exchange(int master, const char *text)
{
    if (write(master, text, strlen(text)) != (ssize_t)strlen(text))
        return 0;
    struct pollfd fd = {master, POLLIN, 0};
    int result = poll(&fd, 1, 2000);
    char buffer[256];
    ssize_t size = result > 0 ? read(master, buffer, sizeof(buffer) - 1) : -1;
    if (size <= 0) {
        fprintf(stderr, "PTY read result=%d events=%x size=%zd errno=%d\n",
                result, fd.revents, size, errno);
        return 0;
    }
    buffer[size] = 0;
    printf("PTY received: %s", buffer);
    return strstr(buffer, text[0] == 'b' ? "before" : "after") != NULL;
}

int main(int argc, char **argv)
{
    if (argc != 3 || (strcmp(argv[2], "ordinary") != 0 && strcmp(argv[2], "noctty") != 0)) {
        fprintf(stderr, "usage: native-pty-lifetime CAT-PATH ordinary|noctty\n");
        return 2;
    }
    int master, slave, ready[2];
    char name[256];
    if (openpty(&master, &slave, name, NULL, NULL) != 0 || pipe(ready) != 0) {
        perror("openpty/pipe");
        return 2;
    }
    struct termios attributes;
    if (tcgetattr(slave, &attributes) != 0) {
        perror("tcgetattr");
        return 2;
    }
    attributes.c_lflag &= ~ECHO;
    if (tcsetattr(slave, TCSANOW, &attributes) != 0) {
        perror("tcsetattr");
        return 2;
    }
    pid_t child = fork();
    if (child < 0) {
        perror("fork");
        return 2;
    }
    if (child == 0) {
        close(ready[0]);
        close(master);
        close(slave);
        if (setsid() < 0)
            _exit(110);
        int terminal = open(name, O_RDWR);
        if (terminal < 0 || dup2(terminal, 0) < 0 || dup2(terminal, 1) < 0 || dup2(terminal, 2) < 0)
            _exit(111);
        if (terminal > 2)
            close(terminal);
        if (ioctl(0, TIOCSCTTY, (void *)0) != 0 || tcgetsid(0) != getsid(0))
            _exit(114);
        if (write(ready[1], "r", 1) != 1)
            _exit(112);
        close(ready[1]);
        execl(argv[1], argv[1], "-u", (char *)NULL);
        _exit(113);
    }
    close(ready[1]);
    close(slave);
    char byte;
    int valid = read(ready[0], &byte, 1) == 1;
    close(ready[0]);
    printf("parent=%ld child=%ld slave=%s mode=%s\n",
           (long)getpid(), (long)child, name, argv[2]);
    printf("parent_sid=%ld child_sid=%ld terminal_sid=%ld\n",
           (long)getsid(0), (long)getsid(child), (long)tcgetsid(master));
    valid = valid && exchange(master, "before\n");
    if (valid) {
        int flags = O_RDONLY;
        if (strcmp(argv[2], "noctty") == 0)
            flags |= O_NOCTTY;
        int extra = open(name, flags);
        printf("secondary_fd=%d parent_sid=%ld terminal_sid=%ld errno=%d\n",
               extra, (long)getsid(0), (long)tcgetsid(master), errno);
        if (extra < 0) {
            perror("secondary slave open");
            valid = 0;
        } else {
            if (close(extra) != 0)
                valid = 0;
            usleep(100000);
            valid = valid && exchange(master, "after\n");
        }
    }
    int status = 0;
    if (waitpid(child, &status, WNOHANG) == 0) {
        write(master, "\004", 1);
        for (int attempt = 0; attempt != 100; ++attempt) {
            if (waitpid(child, &status, WNOHANG) == child)
                goto drained;
            usleep(10000);
        }
        kill(child, SIGTERM);
        waitpid(child, &status, 0);
        valid = 0;
    }
drained:
    printf("child_wait_status=%d exited=%d code=%d signaled=%d signal=%d valid=%d\n",
           status, WIFEXITED(status), WIFEXITED(status) ? WEXITSTATUS(status) : -1,
           WIFSIGNALED(status), WIFSIGNALED(status) ? WTERMSIG(status) : 0, valid);
    close(master);
    return valid && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 1;
}

#include <sys/cygwin.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <pty.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int await_text(int terminal, FILE *log, const char *wanted)
{
    char data[65536] = {0};
    size_t used = 0;
    time_t end = time(NULL) + 15;
    while (time(NULL) < end) {
        fd_set readset;
        struct timeval timeout = {1, 0};
        FD_ZERO(&readset);
        FD_SET(terminal, &readset);
        int selected = select(terminal + 1, &readset, NULL, NULL, &timeout);
        if (selected < 0)
            return 0;
        if (!selected)
            continue;
        ssize_t count = read(terminal, data + used, sizeof(data) - used - 1);
        if (count <= 0)
            return 0;
        fwrite(data + used, 1, (size_t)count, log);
        fflush(log);
        used += (size_t)count;
        data[used] = 0;
        if (strstr(data, wanted))
            return 1;
        if (used > sizeof(data) / 2) {
            memmove(data, data + used - 1024, 1024);
            used = 1024;
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    int master = -1, slave = -1, status = 0, passed = 0;
    struct winsize size = {30, 100, 0, 0};
    if (argc != 3 && argc != 4)
        return 2;
    int curses_mode = argc == 4 && strcmp(argv[3], "curses") == 0;
    FILE *log = fopen("pty-output.bin", "wb");
    if (!log)
        return 3;
    if (openpty(&master, &slave, NULL, NULL, &size) != 0) {
        perror("openpty");
        fclose(log);
        return 4;
    }
    pid_t child = fork();
    if (child == 0) {
        close(master);
        if (setsid() < 0 || ioctl(slave, TIOCSCTTY, 0) < 0)
            _exit(5);
        for (int fd = 0; fd != 3; ++fd)
            if (dup2(slave, fd) < 0)
                _exit(6);
        if (slave > 2)
            close(slave);
        if (curses_mode)
            execl(argv[1], argv[1], argv[2], (char *)NULL);
        else
            execl(argv[1], argv[1], "--ignorercfiles", "--nonewlines", argv[2], (char *)NULL);
        _exit(7);
    }
    close(slave);
    if (child < 0) {
        perror("fork");
        close(master);
        fclose(log);
        return 8;
    }
    if (await_text(master, log, curses_mode ? "curses-cpp-ready" : "before")) {
        FILE *ready = fopen("editor-ready.json", "wb");
        if (ready) {
            fprintf(ready, "{\"windows_pid\":%lu}\n", (unsigned long)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, child));
            fclose(ready);
            time_t end = time(NULL) + 20;
            while (access("continue", F_OK) != 0 && time(NULL) < end)
                usleep(50000);
            const char input[] = "\005 after \316\273\017";
            int interacted = access("continue", F_OK) == 0;
            if (curses_mode)
                interacted = interacted && write(master, "\r", 1) == 1;
            else
                interacted = interacted && write(master, input, sizeof(input) - 1) == sizeof(input) - 1 &&
                    await_text(master, log, "Write to File:") && write(master, "\r", 1) == 1 &&
                    await_text(master, log, "Wrote") && write(master, "\030", 1) == 1;
            if (interacted) {
                end = time(NULL) + 10;
                while (time(NULL) < end) {
                    if (waitpid(child, &status, WNOHANG) == child) {
                        passed = WIFEXITED(status) && WEXITSTATUS(status) == 0;
                        child = -1;
                        break;
                    }
                    usleep(50000);
                }
            }
        }
    }
    if (child > 0) {
        kill(child, SIGKILL);
        waitpid(child, &status, 0);
    }
    close(master);
    fclose(log);
    return passed ? 0 : 9;
}

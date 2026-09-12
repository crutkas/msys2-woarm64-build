#include <errno.h>
#include <pty.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    int master, slave;
    struct winsize size = {24, 80, 0, 0};
    if (argc != 2)
        return 90;
    if (openpty(&master, &slave, NULL, NULL, &size) != 0) {
        perror("openpty");
        return 91;
    }
    pid_t child = fork();
    if (child < 0) {
        perror("fork");
        return 92;
    }
    if (child == 0) {
        close(master);
        if (dup2(slave, STDIN_FILENO) != STDIN_FILENO) {
            perror("dup2");
            _exit(93);
        }
        close(slave);
        execl(argv[1], argv[1], "size", (char *)NULL);
        perror("execl");
        _exit(94);
    }
    close(slave);
    int status;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    close(master);
    if (waited != child || !WIFEXITED(status))
        return 95;
    return WEXITSTATUS(status);
}

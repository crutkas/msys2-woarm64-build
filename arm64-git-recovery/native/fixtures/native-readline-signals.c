#include <sys/cygwin.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <errno.h>
#include <locale.h>
#include <pty.h>
#include <setjmp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <readline/readline.h>
#include <readline/history.h>

static sigjmp_buf interrupt_return;
static volatile sig_atomic_t interrupts, resize_signals;
static int resize_reported, expected_rows, expected_columns;
static struct termios original;

static int same_terminal(const struct termios *a, const struct termios *b)
{
    return a->c_iflag == b->c_iflag && a->c_oflag == b->c_oflag &&
        a->c_cflag == b->c_cflag && a->c_lflag == b->c_lflag &&
        memcmp(a->c_cc, b->c_cc, NCCS) == 0 &&
        cfgetispeed(a) == cfgetispeed(b) && cfgetospeed(a) == cfgetospeed(b);
}

static int restored(void)
{
    struct termios current;
    return tcgetattr(STDIN_FILENO, &current) == 0 && same_terminal(&original, &current);
}

static void on_interrupt(int signo)
{
    (void)signo;
    ++interrupts;
    siglongjmp(interrupt_return, 1);
}

static void on_resize(int signo)
{
    (void)signo;
    ++resize_signals;
}

static int event_hook(void)
{
    if (resize_signals && !resize_reported) {
        int rows = 0, columns = 0;
        rl_get_screen_size(&rows, &columns);
        if (rows == expected_rows && columns == expected_columns) {
            resize_reported = 1;
            printf("\nresized:%d:%d\n", rows, columns);
            fflush(stdout);
            rl_on_new_line();
            rl_redisplay();
        }
    }
    return 0;
}

static int editor(const char *report_path)
{
    if (sizeof(long) != 8 || sizeof(void *) != 8 ||
        !setlocale(LC_ALL, "C.UTF-8") || MB_CUR_MAX <= 1 ||
        tcgetattr(STDIN_FILENO, &original) != 0 || !isatty(STDIN_FILENO))
        return 20;
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    sigemptyset(&action.sa_mask);
    action.sa_handler = on_interrupt;
    if (sigaction(SIGINT, &action, NULL) != 0)
        return 21;
    action.sa_handler = on_resize;
    if (sigaction(SIGWINCH, &action, NULL) != 0)
        return 22;
    rl_catch_signals = 1;
    rl_catch_sigwinch = 1;
    rl_readline_name = "combined-runtime-readline-signal-proof";
    using_history();
    char *line = readline("initial-ready> ");
    if (!line || strcmp(line, "initial \316\273\344\270\255") || !restored())
        return 23;
    add_history(line);
    free(line);
    for (int iteration = 0; iteration < 3; ++iteration) {
        expected_rows = 37 + iteration;
        expected_columns = 91 + iteration;
        resize_signals = 0;
        resize_reported = 0;
        rl_event_hook = event_hook;
        char prompt[48];
        snprintf(prompt, sizeof(prompt), "resize-%d> ", iteration);
        line = readline(prompt);
        rl_event_hook = NULL;
        if (!line || strcmp(line, "resized \316\273") ||
            !resize_reported || !resize_signals || !restored())
            return 24;
        free(line);
        if (sigsetjmp(interrupt_return, 1) == 0) {
            snprintf(prompt, sizeof(prompt), "interrupt-%d> ", iteration);
            line = readline(prompt);
            free(line);
            return 25;
        }
        /* Readline must restore the terminal before chaining our SIGINT handler. */
        if (!restored())
            return 26;
        rl_free_line_state();
        rl_cleanup_after_signal();
        printf("\ninterrupt-restored-%d\n", iteration);
        fflush(stdout);
        snprintf(prompt, sizeof(prompt), "reentry-%d> ", iteration);
        line = readline(prompt);
        if (!line || strcmp(line, "after \316\273\344\270\255") || !restored())
            return 27;
        add_history(line);
        free(line);
    }
    line = readline("history-ready> ");
    if (!line || strcmp(line, "after \316\273\344\270\255") || !restored() ||
        interrupts != 3 || history_length != 4 || rl_readline_version != 0x0803)
        return 28;
    free(line);
    FILE *report = fopen(report_path, "wb");
    if (!report)
        return 29;
    int written = fprintf(report,
        "{\"passed\":true,\"readline_version\":%d,\"sigint\":%d,"
        "\"sigwinch_roundtrips\":3,\"restore_before_caller_sigint_handler\":true,"
        "\"normal_return_restored\":true,\"reentry_unicode\":true,\"history_entries\":%d}\n",
        rl_readline_version, (int)interrupts, history_length);
    if (fclose(report) != 0 || written < 0)
        return 30;
    clear_history();
    return 0;
}

static int await_text(int terminal, FILE *log, const char *wanted)
{
    char data[65536] = {0};
    size_t used = 0;
    time_t deadline = time(NULL) + 20;
    while (time(NULL) < deadline) {
        fd_set set;
        FD_ZERO(&set);
        FD_SET(terminal, &set);
        struct timeval timeout = {1, 0};
        int ready = select(terminal + 1, &set, NULL, NULL, &timeout);
        if (ready < 0 && errno == EINTR)
            continue;
        if (ready < 0)
            return 0;
        if (!ready)
            continue;
        ssize_t count = read(terminal, data + used, sizeof(data) - used - 1);
        if (count <= 0)
            return 0;
        if (fwrite(data + used, 1, (size_t)count, log) != (size_t)count || fflush(log) != 0)
            return 0;
        used += (size_t)count;
        data[used] = 0;
        if (strstr(data, wanted))
            return 1;
        if (used > sizeof(data) / 2) {
            memmove(data, data + used - 1024, 1024);
            used = 1024;
        }
    }
    fprintf(stderr, "Timeout awaiting PTY marker: %s\n", wanted);
    return 0;
}

static int send_text(int terminal, const char *text)
{
    size_t length = strlen(text);
    return write(terminal, text, length) == (ssize_t)length;
}

static int controller(const char *program, const char *report_path, const char *signal_mode)
{
    int master = -1, slave = -1, status = 0, passed = 0, phase = 0;
    struct winsize size = {30, 80, 0, 0};
    struct termios before, after;
    FILE *log = fopen("pty-output.bin", "wb");
    if (!log || openpty(&master, &slave, NULL, NULL, &size) != 0 ||
        tcgetattr(slave, &before) != 0)
        return 2;
    pid_t child = fork();
    if (child == 0) {
        close(master);
        if (setsid() < 0 || ioctl(slave, TIOCSCTTY, 0) < 0 || tcsetpgrp(slave, getpid()) != 0)
            _exit(3);
        for (int fd = 0; fd != 3; ++fd)
            if (dup2(slave, fd) < 0)
                _exit(4);
        if (slave > 2)
            close(slave);
        execl(program, program, "--editor", report_path, (char *)NULL);
        _exit(5);
    }
    if (child < 0)
        return 6;
    if (!await_text(master, log, "initial-ready> "))
        goto done;
    phase = 1;
    FILE *ready = fopen("editor-ready.json", "wb");
    if (!ready)
        goto done;
    fprintf(ready, "{\"windows_pid\":%lu}\n",
            (unsigned long)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, child));
    if (fclose(ready) != 0)
        goto done;
    time_t deadline = time(NULL) + 30;
    while (access("continue", F_OK) != 0 && time(NULL) < deadline)
        usleep(50000);
    if (access("continue", F_OK) != 0 ||
        !send_text(master, "initial \316\273\344\270\255X\177\r"))
        goto done;
    for (int iteration = 0; iteration < 3; ++iteration) {
        char wanted[64];
        phase = 10 + iteration * 10;
        snprintf(wanted, sizeof(wanted), "resize-%d> ", iteration);
        if (!await_text(master, log, wanted))
            goto done;
        size.ws_row = (unsigned short)(37 + iteration);
        size.ws_col = (unsigned short)(91 + iteration);
        if (ioctl(master, TIOCSWINSZ, &size) != 0 || kill(child, SIGWINCH) != 0)
            goto done;
        snprintf(wanted, sizeof(wanted), "resized:%d:%d", size.ws_row, size.ws_col);
        if (!await_text(master, log, wanted) || !send_text(master, "resized \316\273\r"))
            goto done;
        phase += 1;
        snprintf(wanted, sizeof(wanted), "interrupt-%d> ", iteration);
        if (!await_text(master, log, wanted) || !send_text(master, "discard-this-line") ||
            !await_text(master, log, "discard-this-line"))
            goto done;
        if (!strcmp(signal_mode, "tty")) {
            unsigned char intr = before.c_cc[VINTR];
            if (write(master, &intr, 1) != 1)
                goto done;
        } else if (kill(child, SIGINT) != 0) {
            goto done;
        }
        snprintf(wanted, sizeof(wanted), "interrupt-restored-%d", iteration);
        if (!await_text(master, log, wanted))
            goto done;
        /* The marker and next prompt may share a read; wait for the actual tty mode. */
        deadline = time(NULL) + 5;
        do {
            if (tcgetattr(slave, &after) != 0)
                goto done;
            if (!(after.c_lflag & (ICANON | ECHO)))
                break;
            usleep(10000);
        } while (time(NULL) < deadline);
        if ((after.c_lflag & (ICANON | ECHO)) ||
            !send_text(master, "after \316\273\344\270\255X\177\177\344\270\255\r"))
            goto done;
    }
    phase = 50;
    if (!await_text(master, log, "history-ready> ") || !send_text(master, "\020\r"))
        goto done;
    deadline = time(NULL) + 15;
    while (time(NULL) < deadline) {
        if (waitpid(child, &status, WNOHANG) == child) {
            child = -1;
            passed = WIFEXITED(status) && WEXITSTATUS(status) == 0 &&
                tcgetattr(slave, &after) == 0 && same_terminal(&before, &after);
            break;
        }
        usleep(50000);
    }
done:
    if (child > 0) {
        kill(child, SIGKILL);
        waitpid(child, &status, 0);
    }
    FILE *result = fopen("controller.json", "wb");
    if (result) {
        fprintf(result, "{\"passed\":%s,\"phase\":%d,\"wait_status\":%d,"
                "\"signal_mode\":\"%s\",\"external_terminal_restored\":%s}\n",
                passed ? "true" : "false", phase, status, signal_mode, passed ? "true" : "false");
        fclose(result);
    }
    close(master);
    close(slave);
    fclose(log);
    return passed ? 0 : 10;
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "--editor"))
        return editor(argv[2]);
    if (argc == 3 && (!strcmp(argv[2], "tty") || !strcmp(argv[2], "kill")))
        return controller(argv[0], argv[1], argv[2]);
    return 1;
}

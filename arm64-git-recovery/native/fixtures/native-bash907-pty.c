#include <sys/cygwin.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <errno.h>
#include <dirent.h>
#include <pty.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static char pending[262144];
static size_t used;
static FILE *transcript, *cases;
static int master = -1, passed, failed;

static int await(const char *text, int seconds)
{
    time_t deadline = time(NULL) + seconds;
    while (time(NULL) < deadline) {
        char *found = strstr(pending, text);
        if (found) {
            size_t consumed = (size_t)(found - pending) + strlen(text);
            memmove(pending, pending + consumed, used - consumed);
            used -= consumed;
            pending[used] = '\0';
            return 1;
        }
        fd_set set;
        FD_ZERO(&set);
        FD_SET(master, &set);
        struct timeval timeout = {1, 0};
        int result = select(master + 1, &set, NULL, NULL, &timeout);
        if (result < 0 && errno == EINTR)
            continue;
        if (result < 0 || used + 1 >= sizeof(pending))
            return 0;
        if (!result)
            continue;
        ssize_t count = read(master, pending + used, sizeof(pending) - used - 1);
        if (count <= 0)
            return 0;
        if (fwrite(pending + used, 1, (size_t)count, transcript) != (size_t)count || fflush(transcript) != 0)
            return 0;
        used += (size_t)count;
        pending[used] = '\0';
    }
    fprintf(stderr, "Timeout waiting for %s; buffered: %s\n", text, pending);
    return 0;
}

static int send(const char *data)
{
    size_t n = strlen(data);
    return write(master, data, n) == (ssize_t)n;
}

static int record(const char *name, int okay)
{
    fprintf(cases, "%s\t%s\n", name, okay ? "PASS" : "FAIL");
    fflush(cases);
    if (okay) ++passed;
    else ++failed;
    return okay;
}

static int command(const char *name, const char *text, const char *answer)
{
    if (!send(text) || !send("\r"))
        return record(name, 0);
    int okay = await(answer, 25);
    int prompt = await("BASH907__> ", 25);
    return record(name, okay && prompt);
}

static int same_termios(const struct termios *a, const struct termios *b)
{
    return a->c_iflag == b->c_iflag && a->c_oflag == b->c_oflag &&
        a->c_cflag == b->c_cflag && a->c_lflag == b->c_lflag &&
        !memcmp(a->c_cc, b->c_cc, NCCS) &&
        cfgetispeed(a) == cfgetispeed(b) && cfgetospeed(a) == cfgetospeed(b);
}

static int group_members(pid_t session, pid_t foreground, const char *phase, int emit, const char *pipeline)
{
    DIR *directory = opendir("/proc");
    if (!directory)
        return 0;
    FILE *record_file = emit ? fopen("group-members.tsv", "ab") : NULL;
    if (emit && !record_file) {
        closedir(directory);
        return 0;
    }
    int members = 0, sleeps = 0, cats = 0;
    struct dirent *entry;
    while ((entry = readdir(directory)) != NULL) {
        char *end = NULL;
        long pid = strtol(entry->d_name, &end, 10);
        if (pid <= 0 || !end || *end)
            continue;
        char path[80], statbuf[4096], image[4096];
        snprintf(path, sizeof(path), "/proc/%ld/stat", pid);
        FILE *statfile = fopen(path, "rb");
        if (!statfile)
            continue;
        char *read_result = fgets(statbuf, sizeof(statbuf), statfile);
        fclose(statfile);
        if (!read_result)
            continue;
        char *after = strrchr(statbuf, ')');
        char state;
        long ppid, pgid, sid;
        if (!after || sscanf(after + 2, "%c %ld %ld %ld", &state, &ppid, &pgid, &sid) != 4 || sid != session)
            continue;
        snprintf(path, sizeof(path), "/proc/%ld/exe", pid);
        ssize_t length = readlink(path, image, sizeof(image) - 1);
        if (length < 0) image[0] = '\0';
        else image[length] = '\0';
        pid_t api_group = getpgid((pid_t)pid);
        unsigned long winpid = (unsigned long)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, (pid_t)pid);
        if (emit)
            fprintf(record_file, "%s\t%ld\t%lu\t%ld\t%ld\t%ld\t%ld\t%c\t%s\n",
                    phase, pid, winpid, ppid, pgid, (long)api_group, sid, state, image);
        if (pgid == foreground) {
            ++members;
            if (strstr(image, "/sleep") || strstr(image, "\\sleep")) ++sleeps;
            if (strstr(image, "/cat") || strstr(image, "\\cat")) ++cats;
        }
    }
    if (record_file) fclose(record_file);
    closedir(directory);
    int expected_members = strchr(pipeline, '|') ? 2 : 1;
    int expected_sleeps = strstr(pipeline, "sleep") ? 1 : 0;
    const char *second = strstr(pipeline, "|");
    if (expected_sleeps && second && strstr(second, "sleep") && strstr(pipeline, "sleep") < second)
        expected_sleeps = 2;
    int expected_cats = strstr(pipeline, "cat") ? 1 : 0;
    return members >= expected_members && sleeps >= expected_sleeps && cats >= expected_cats;
}

int main(int argc, char **argv)
{
    if (argc != 3)
        return 2;
    int slave = -1, status = 0;
    struct winsize size = {30, 100, 0, 0};
    struct termios before, after;
    transcript = fopen("pty-output.bin", "wb");
    cases = fopen("cases.tsv", "wb");
    if (!transcript || !cases || openpty(&master, &slave, NULL, NULL, &size) ||
        tcgetattr(slave, &before))
        return 3;
    pid_t child = fork();
    if (child == 0) {
        close(master);
        if (setsid() < 0 || ioctl(slave, TIOCSCTTY, 0) < 0 || tcsetpgrp(slave, getpid()))
            _exit(4);
        for (int fd = 0; fd < 3; ++fd)
            if (dup2(slave, fd) < 0) _exit(5);
        if (slave > 2) close(slave);
        execl(argv[1], argv[1], "--noprofile", "--norc", "-i", (char *)NULL);
        _exit(6);
    }
    if (child < 0)
        return 7;
    if (!await("BASH907__> ", 25))
        goto done;
    FILE *ready = fopen("editor-ready.json", "wb");
    if (!ready) goto done;
    fprintf(ready, "{\"windows_pid\":%lu}\n",
            (unsigned long)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, child));
    fclose(ready);
    time_t deadline = time(NULL) + 30;
    while (access("continue", F_OK) && time(NULL) < deadline) usleep(50000);
    if (access("continue", F_OK)) goto done;
    if (!command("native-shell-identity",
        "[[ $BASH_VERSION == 5.3.15* && $MACHTYPE == aarch64-pc-cygwin && $- == *i* && $- == *m* ]]; printf '\\nCASE:identity:%s\\n' \"$?\"",
        "\r\nCASE:identity:0\r\n")) goto done;
    if (getenv("BASH907_FOCUS_JOBS"))
        goto jobs;
    if (!command("pipeline-status-default",
        "(exit 7) | (exit 0); s=$? p=(\"${PIPESTATUS[@]}\"); [[ $s == 0 && ${p[*]} == '7 0' ]]; printf '\\nCASE:pipe:%s\\n' \"$?\"",
        "\r\nCASE:pipe:0\r\n")) goto done;
    if (!command("pipefail-status",
        "set -o pipefail; (exit 7) | (exit 0); s=$? p=(\"${PIPESTATUS[@]}\"); set +o pipefail; [[ $s == 7 && ${p[*]} == '7 0' ]]; printf '\\nCASE:pipefail:%s\\n' \"$?\"",
        "\r\nCASE:pipefail:0\r\n")) goto done;
    if (!command("subshell-command-substitution",
        "x=outer; y=$(printf 'value'; exit 9); s=$?; (x=inner; [[ $x == inner ]]); [[ $x == outer && $y == value && $s == 9 ]]; printf '\\nCASE:substitution:%s\\n' \"$?\"",
        "\r\nCASE:substitution:0\r\n")) goto done;
    if (!command("heredoc-expansion",
        "v=world; read -r line <<EOF\nhello $v\nEOF\n[[ $line == 'hello world' ]]; printf '\\nCASE:heredoc:%s\\n' \"$?\"",
        "\r\nCASE:heredoc:0\r\n")) goto done;
    if (!command("heredoc-quoted",
        "read -r line <<'EOF'\n$v literal\nEOF\n[[ $line == '$v literal' ]]; printf '\\nCASE:quoted:%s\\n' \"$?\"",
        "\r\nCASE:quoted:0\r\n")) goto done;
    if (!command("globbing",
        "printf a > owned-a.txt; printf b > owned-b.txt; printf h > .owned-hidden; a=(owned-*.txt); [[ ${#a[@]} == 2 && ${a[0]} == owned-a.txt && ${a[1]} == owned-b.txt ]]; printf '\\nCASE:glob:%s\\n' \"$?\"",
        "\r\nCASE:glob:0\r\n")) goto done;
    if (!command("quoted-space-unicode-path",
        "mkdir 'owned space'; printf '%s' 'path value' > 'owned space/value.txt'; read -r value < 'owned space/value.txt'; [[ $value == 'path value' ]]; printf '\\nCASE:path:%s\\n' \"$?\"",
        "\r\nCASE:path:0\r\n")) goto done;
    if (!command("msys-windows-path-roundtrip",
        "p=$PWD; w=$(pwd -W); cd \"$w\" && [[ $PWD == \"$p\" && $w == [A-Za-z]:/* ]]; printf '\\nCASE:winpath:%s\\n' \"$?\"",
        "\r\nCASE:winpath:0\r\n")) goto done;
    if (!command("msys-native-path-translation",
        "w=$(pwd -W); printf native > \"$w/owned-win.txt\"; [[ $(<owned-win.txt) == native && $(/usr/bin/cat.exe \"$w/owned-win.txt\") == native ]]; printf '\\nCASE:translation:%s\\n' \"$?\"",
        "\r\nCASE:translation:0\r\n")) goto done;
    /* Real editing: erase a CJK character, reinsert it, then accept the command. */
    if (!command("readline-unicode-edit",
        "v='lambda \316\273\344\270\255X\177\177\344\270\255'; [[ $v == 'lambda \316\273\344\270\255' ]]; printf '\\nCASE:unicode:%s\\n' \"$?\"",
        "\r\nCASE:unicode:0\r\n")) goto done;
    if (!command("readline-history", "\020", "\r\nCASE:unicode:0\r\n")) goto done;
    if (!send("discard-no-command") || !await("discard-no-command", 5)) goto done;
    unsigned char intr = before.c_cc[VINTR];
    if (write(master, &intr, 1) != 1 || !await("BASH907__> ", 15)) goto done;
    if (!command("ctrl-c-at-prompt",
        "s=$?; [[ $s == 130 ]]; printf '\\nCASE:prompt-interrupt:%s:%s\\n' \"$?\" \"$s\"",
        "\r\nCASE:prompt-interrupt:0:130\r\n")) goto done;
    size.ws_row = 41; size.ws_col = 87;
    if (ioctl(master, TIOCSWINSZ, &size) || kill(child, SIGWINCH)) goto done;
    usleep(150000);
    if (!command("window-resize",
        "[[ $LINES == 41 && $COLUMNS == 87 ]]; printf '\\nCASE:resize:%s:%s:%s\\n' \"$?\" \"$LINES\" \"$COLUMNS\"",
        "\r\nCASE:resize:0:41:87\r\n")) goto done;
jobs:
    const char *pipeline = getenv("BASH907_PIPELINE");
    if (!pipeline) pipeline = "sleep 60 | cat";
    if (!send(pipeline) || !send("\r") || !await(pipeline, 10)) goto done;
    pid_t initial_foreground = -1;
    deadline = time(NULL) + 15;
    int pipeline_ready = 0;
    do {
        if (ioctl(master, TIOCGPGRP, &initial_foreground) == 0 && initial_foreground > 0 &&
            initial_foreground != child && group_members(child, initial_foreground, "initial", 0, pipeline)) {
            pipeline_ready = 1;
            break;
        }
        usleep(10000);
    } while (time(NULL) < deadline);
    group_members(child, initial_foreground, "before-suspend-or-signal", 1, pipeline);
    if (!pipeline_ready) {
        fprintf(stderr, "Pipeline members were not ready in foreground group %ld\n", (long)initial_foreground);
        goto done;
    }
    if (getenv("BASH907_DELIVERY_ONLY"))
        goto foreground_signal;
    unsigned char susp = before.c_cc[VSUSP];
    if (write(master, &susp, 1) != 1 || !await("BASH907__> ", 15)) goto done;
    if (!command("job-suspend",
        "j=$(jobs -s); [[ $j == *Stopped* ]]; printf '\\nCASE:stopped:%s\\n' \"$?\"",
        "\r\nCASE:stopped:0\r\n")) goto done;
    if (!command("job-background-resume",
        "bg %+; j=$(jobs -r); jobs -p %+ > foreground-pgid.txt; [[ $j == *Running* ]]; printf '\\nCASE:background:%s\\n' \"$?\"",
        "\r\nCASE:background:0\r\n")) goto done;
    if (!send("fg %+\r") || !await(pipeline, 15)) goto done;
foreground_signal:
    pid_t foreground = -1;
    int master_error = 0;
    deadline = time(NULL) + 5;
    do {
        errno = 0;
        if (ioctl(master, TIOCGPGRP, &foreground) != 0) {
            master_error = errno;
            foreground = -1;
        }
        if (foreground > 0 && foreground != child) break;
        usleep(10000);
    } while (time(NULL) < deadline);
    errno = 0;
    pid_t slave_foreground = tcgetpgrp(slave);
    int slave_error = errno;
    long jobs_pgid = -1;
    if (getenv("BASH907_DELIVERY_ONLY")) {
        jobs_pgid = initial_foreground;
    } else {
        FILE *pgid_file = fopen("foreground-pgid.txt", "rb");
        if (!pgid_file || fscanf(pgid_file, "%ld", &jobs_pgid) != 1) goto done;
        fclose(pgid_file);
    }
    group_members(child, foreground, "immediately-before-SIGINT", 1, pipeline);
    fprintf(stderr, "shell_posix_pid=%ld master_foreground_pgid=%ld master_errno=%d slave_foreground_pgid=%ld slave_errno=%d jobs_pgid=%ld pipeline=%s\n",
            (long)child, (long)foreground, master_error, (long)slave_foreground, slave_error, jobs_pgid, pipeline);
    fflush(stderr);
    if (foreground > 0 && foreground != jobs_pgid) goto done;
    if (jobs_pgid <= 0 || jobs_pgid == child) goto done;
    intr = before.c_cc[VINTR];
    if (getenv("BASH907_DIRECT_GROUP_SIGNAL")) {
        if (kill(-(pid_t)jobs_pgid, SIGINT)) goto done;
    } else if (write(master, &intr, 1) != 1) goto done;
    if (!await("BASH907__> ", 15)) goto done;
    command("job-foreground-ctrl-c-pipeline",
        "s=$? p=(\"${PIPESTATUS[@]}\"); printf '\\nRAW_PIPESTATUS:%s\\n' \"${p[*]}\"; [[ $s == 130 ]]; printf '\\nCASE:foreground:%s:%s\\n' \"$?\" \"$s\"",
        "\r\nCASE:foreground:0:130\r\n");
    if (!command("background-wait-status",
        "(exit 17) & p=$!; wait \"$p\"; s=$?; [[ $s == 17 ]]; printf '\\nCASE:wait:%s:%s\\n' \"$?\" \"$s\"",
        "\r\nCASE:wait:0:17\r\n")) goto done;
    if (!send("exit 0\r")) goto done;
    deadline = time(NULL) + 15;
    while (time(NULL) < deadline) {
        if (waitpid(child, &status, WNOHANG) == child) {
            child = -1;
            record("normal-exit-terminal-restored", WIFEXITED(status) && WEXITSTATUS(status) == 0 &&
                   tcgetattr(slave, &after) == 0 && same_termios(&before, &after));
            break;
        }
        usleep(50000);
    }
done:
    if (child > 0) {
        kill(-child, SIGKILL);
        kill(child, SIGKILL);
        waitpid(child, &status, 0);
        ++failed;
    }
    FILE *report = fopen(argv[2], "wb");
    if (report) {
        fprintf(report, "{\"passed\":%s,\"passes\":%d,\"failures\":%d,\"wait_status\":%d}\n",
                failed == 0 ? "true" : "false", passed, failed, status);
        fclose(report);
    }
    fclose(cases); fclose(transcript);
    close(master); close(slave);
    return failed == 0 ? 0 : 1;
}

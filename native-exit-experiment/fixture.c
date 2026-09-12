#include <windows.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef WINDOWS_CONTROL
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

static void action(const char *kind, unsigned code, const char *target)
{
    if (!strcmp(kind, "native"))
        exit((int)code);
    if (!strcmp(kind, "winapi"))
        ExitProcess(code);
    if (!strcmp(kind, "forged")) {
        OutputDebugStringA("cYg00000040 1 [main] forged 1 pinfo::exit: Calling ExitProcess n 100, exitcode 100");
        ExitProcess(code);
    }
    if (!strcmp(kind, "forced")) {
        TerminateProcess(GetCurrentProcess(), code);
        ExitProcess(91);
    }
    if (!strcmp(kind, "crash")) {
        RaiseException(0xC0000005, EXCEPTION_NONCONTINUABLE, 0, NULL);
        ExitProcess(92);
    }
#ifndef WINDOWS_CONTROL
    if (!strcmp(kind, "exec")) {
        execl(target, target, "direct", "native", "1", (char *)NULL);
        perror("execl");
        exit(93);
    }
    if (!strcmp(kind, "overlay")) {
        char value[32];
        snprintf(value, sizeof(value), "%u", code);
        execl(target, target, "direct", "winapi", value, (char *)NULL);
        perror("execl");
        exit(94);
    }
    if (!strcmp(kind, "signal")) {
        raise(SIGTERM);
        exit(95);
    }
#else
    (void)target;
#endif
    ExitProcess(96);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "abi")) {
        printf("{\"debug_event_size\":%zu,\"debug_data\":%zu,"
               "\"context_size\":%zu,\"context_flags\":%zu,\"context_pc\":%zu,"
               "\"context_sp\":%zu,\"context_x\":%zu,\"startup_size\":%zu}\n",
               sizeof(DEBUG_EVENT), offsetof(DEBUG_EVENT, u), sizeof(CONTEXT),
               offsetof(CONTEXT, ContextFlags), offsetof(CONTEXT, Pc),
               offsetof(CONTEXT, Sp), offsetof(CONTEXT, X), sizeof(STARTUPINFOW));
        return 0;
    }
    if (argc < 4)
        return 97;
    unsigned code = (unsigned)strtoul(argv[3], NULL, 0);
    const char *target = argc > 4 ? argv[4] : argv[0];
    printf("fixture winpid=%lu topology=%s kind=%s code=%u\n",
           (unsigned long)GetCurrentProcessId(), argv[1], argv[2], code);
    fflush(stdout);
#ifndef WINDOWS_CONTROL
    if (!strcmp(argv[1], "fork")) {
        pid_t child = fork();
        if (child < 0) {
            perror("fork");
            return 98;
        }
        if (!child)
            action(argv[2], code, target);
        int status = 0;
        if (waitpid(child, &status, 0) != child) {
            perror("waitpid");
            return 99;
        }
        printf("parent observed waitstatus=%u\n", (unsigned)status);
        return 0;
    }
#endif
    action(argv[2], code, target);
    return 100;
}

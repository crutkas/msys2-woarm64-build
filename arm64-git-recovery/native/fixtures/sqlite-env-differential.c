#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static void inspect(const char *phase) {
    const char *names[] = {"WOARM64_ENV_INHERITED", "WOARM64_ENV_NEW", "CCACHE_DISABLE", "TMPDIR", "PATH", "MSYSTEM"};
    char module[MAX_PATH];
    DWORD size = GetModuleFileNameA(GetModuleHandleA("msys-2.0.dll"), module, sizeof(module));
    if (!size || size == sizeof(module)) exit(2);
    printf("native-C PHASE %s runtime=%s long=%zu pointer=%zu\n", phase, module, sizeof(long), sizeof(void *));
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        char win[2048];
        DWORD count = GetEnvironmentVariableA(names[i], win, sizeof(win));
        if (count >= sizeof(win)) exit(2);
        const char *value = getenv(names[i]);
        printf("native-C %s POSIX=<%s> WIN32=<%s>\n", names[i],
               value ? value : "absent", count ? win : "absent");
    }
    fflush(stdout);
}

static void child(char *const argv[]) {
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        exit(3);
    }
    if (pid == 0) {
        execv(argv[0], argv);
        perror("execv");
        _exit(127);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) != pid || !WIFEXITED(status) || WEXITSTATUS(status)) {
        fprintf(stderr, "environment probe child failed: wait status=%d\n", status);
        exit(4);
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--inspect") == 0) {
        inspect("child");
        return 0;
    }
    if (argc != 5) return 2;
    for (int mutate = 0; mutate < 2; ++mutate) {
        if (mutate) {
            if (setenv("WOARM64_ENV_INHERITED", "c-replaced", 1) ||
                setenv("WOARM64_ENV_NEW", "c-new", 1) ||
                setenv("CCACHE_DISABLE", "c-marker", 1)) return 5;
        }
        inspect(mutate ? "mutated" : "inherited");
        char *same[] = {argv[0], "--inspect", NULL};
        char *foreign[] = {argv[1], "--noprofile", "--norc", argv[2], NULL};
        char *native[] = {argv[3], "-B", argv[4], NULL};
        child(same);
        child(foreign);
        child(native);
    }
    return 0;
}

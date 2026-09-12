#include <crypt.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <windows.h>

int main(int argc, char **argv)
{
    const char *setting = "$2b$05$CCCCCCCCCCCCCCCCCCCCC.";
    const char *expected = "$2b$05$CCCCCCCCCCCCCCCCCCCCC.gNn9EDJdrUJF53AHnb.4T9BCvqhUYdW";
    struct crypt_data *state = calloc(1, sizeof(*state));
    char salt[CRYPT_GENSALT_OUTPUT_SIZE], saved[CRYPT_OUTPUT_SIZE], path[4096];
    char entropy[16] = {0};
    char *result;
    FILE *stream;
    if (argc != 2 || !state)
        return 2;
    result = crypt_r("abc", setting, state);
    if (!result || strcmp(result, expected))
        return 3;
    result = crypt_r("abd", setting, state);
    if (!result || !strcmp(result, expected))
        return 4;
    errno = 0;
    if (crypt_r("abc", "$invalid$", state) != NULL || errno != EINVAL)
        return 5;
    if (!crypt_gensalt_rn("$2b$", 5, entropy, sizeof(entropy), salt, sizeof(salt)) ||
        strncmp(salt, "$2b$05$", 7))
        return 6;
    result = crypt_r("abc", salt, state);
    if (!result || strlen(result) >= sizeof(saved))
        return 7;
    strcpy(saved, result);
    result = crypt_r("abc", saved, state);
    if (!result || strcmp(result, saved))
        return 8;
    free(state);
    if (snprintf(path, sizeof(path), "%s/ready", argv[1]) >= (int)sizeof(path))
        return 9;
    stream = fopen(path, "w");
    if (!stream || fprintf(stream, "%lu\n", (unsigned long)GetCurrentProcessId()) < 0 || fclose(stream))
        return 10;
    if (snprintf(path, sizeof(path), "%s/continue", argv[1]) >= (int)sizeof(path))
        return 11;
    for (int i = 0; i < 3000; ++i) {
        if (access(path, F_OK) == 0) {
            puts("native-crypt-consumer-passed");
            return 0;
        }
        usleep(10000);
    }
    return 12;
}

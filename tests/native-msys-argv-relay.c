#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char *translate_existing_drive_path(const char *argument)
{
    const char *path = argument;
    size_t prefix_length = 0;

    const char *equals = strchr(argument, '=');
    if (equals != NULL) {
        prefix_length = (size_t)(equals - argument + 1);
        path = equals + 1;
    } else if (argument[0] == '-' && argument[1] == 'f' &&
               argument[2] == '/') {
        prefix_length = 2;
        path = argument + 2;
    }

    if (path[0] != '/' ||
        !((path[1] >= 'a' && path[1] <= 'z') ||
          (path[1] >= 'A' && path[1] <= 'Z')) ||
        path[2] != '/')
        return strdup(argument);

    size_t path_length = strlen(path);
    char *candidate = malloc(prefix_length + 10 + path_length);
    if (candidate == NULL)
        return NULL;
    memcpy(candidate, argument, prefix_length);
    snprintf(
        candidate + prefix_length,
        10 + path_length,
        "/cygdrive/%c/%s",
        path[1],
        path + 3);

    if (access(candidate + prefix_length, F_OK) == 0)
        return candidate;
    free(candidate);
    return strdup(argument);
}

int main(void)
{
    const char *target = getenv("WOARM64_MSYS_TARGET");
    const char *count_text = getenv("WOARM64_MSYS_ARG_COUNT");
    char *end = NULL;

    if (target == NULL || count_text == NULL)
        return 2;
    errno = 0;
    unsigned long count = strtoul(count_text, &end, 10);
    if (errno != 0 || *count_text == '\0' || *end != '\0' || count > 65535)
        return 2;

    char **arguments = calloc(count + 2, sizeof(*arguments));
    if (arguments == NULL)
        return 2;
    arguments[0] = strdup(target);
    if (arguments[0] == NULL)
        return 2;

    for (unsigned long index = 0; index < count; ++index) {
        char name[64];
        snprintf(name, sizeof(name), "WOARM64_MSYS_ARG_%lu", index);
        const char *encoded = getenv(name);
        if (encoded == NULL || strncmp(encoded, "v1:", 3) != 0)
            return 2;
        arguments[index + 1] = translate_existing_drive_path(encoded + 3);
        if (arguments[index + 1] == NULL)
            return 2;
    }

    execv(target, arguments);
    perror("native MSYS argv relay");
    return 127;
}

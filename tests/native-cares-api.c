#include <ares.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    ares_channel_t *channel = NULL;
    struct ares_options options = {0};
    const char *runtime_version;
    int status;

    status = ares_library_init(ARES_LIB_INIT_ALL);
    if (status != ARES_SUCCESS) {
        fprintf(stderr, "ares_library_init: %s\n", ares_strerror(status));
        return 1;
    }

    runtime_version = ares_version(NULL);
    if (runtime_version == NULL || strcmp(runtime_version, ARES_VERSION_STR) != 0) {
        fprintf(stderr, "c-ares version mismatch: headers=%s runtime=%s\n",
                ARES_VERSION_STR, runtime_version == NULL ? "(null)" : runtime_version);
        ares_library_cleanup();
        return 2;
    }

    status = ares_init_options(&channel, &options, 0);
    if (status != ARES_SUCCESS) {
        fprintf(stderr, "ares_init_options: %s\n", ares_strerror(status));
        ares_library_cleanup();
        return 3;
    }

    printf("c-ares %s native channel initialized\n", runtime_version);
    ares_destroy(channel);
    ares_library_cleanup();
    return 0;
}

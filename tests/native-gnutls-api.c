#include <gnutls/gnutls.h>

#include <stdio.h>
#include <string.h>

int
main(void)
{
    gnutls_session_t session;
    const char *error = NULL;
    const char *runtime_version = gnutls_check_version(NULL);
    int result;

    if (runtime_version == NULL || strcmp(runtime_version, GNUTLS_VERSION) != 0) {
        fprintf(stderr, "GnuTLS header/runtime version mismatch: headers=%s runtime=%s\n",
                GNUTLS_VERSION, runtime_version == NULL ? "(null)" : runtime_version);
        return 1;
    }

    result = gnutls_global_init();
    if (result < 0) {
        fprintf(stderr, "gnutls_global_init failed: %s\n", gnutls_strerror(result));
        return 2;
    }

    result = gnutls_init(&session, GNUTLS_CLIENT);
    if (result < 0) {
        fprintf(stderr, "gnutls_init failed: %s\n", gnutls_strerror(result));
        gnutls_global_deinit();
        return 3;
    }

    result = gnutls_priority_set_direct(session, "NORMAL", &error);
    if (result < 0) {
        fprintf(stderr, "gnutls_priority_set_direct failed at %s: %s\n",
                error == NULL ? "(unknown)" : error, gnutls_strerror(result));
        gnutls_deinit(session);
        gnutls_global_deinit();
        return 4;
    }

    printf("GnuTLS %s native client session initialized\n", runtime_version);
    gnutls_deinit(session);
    gnutls_global_deinit();
    return 0;
}

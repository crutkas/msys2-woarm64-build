#include <iconv.h>
#include <libssh2.h>
#include <stdio.h>
#include <string.h>
#ifdef TEST_LIBINTL
#include <stdint.h>
#include <libintl.h>
#endif

static int supports(LIBSSH2_SESSION *session, int method, const char *wanted)
{
    const char **algorithms = NULL;
    int count = libssh2_session_supported_algs(session, method, &algorithms);
    int found = 0;
    for (int index = 0; index < count; ++index)
        if (strcmp(algorithms[index], wanted) == 0)
            found = 1;
    if (!found)
        fprintf(stderr, "Missing SSH algorithm %s for method %d (count %d)\n", wanted, method, count);
    if (count > 0)
        libssh2_free(session, (void *)algorithms);
    return found;
}

int main(void)
{
#ifdef TEST_LIBINTL
    char formatted[128];
    const char expected_format[] = "hello 123 123 0:0\n";
    int length = libintl_snprintf(formatted, sizeof(formatted), "hello %llu %I64u 0:%d\n",
                                 (uint64_t)123, (uint64_t)123, 0);
    if (length != (int)strlen(expected_format) || strcmp(formatted, expected_format) != 0)
        return 9;
#endif
    char input[] = "A\xc3\xa9\xce\xa9\xf0\x9f\x99\x82";
    const unsigned char expected[] = {0x41, 0, 0xe9, 0, 0xa9, 3, 0x3d, 0xd8, 0x42, 0xde};
    char output[64], *in = input, *out = output;
    size_t in_left = sizeof(input) - 1, out_left = sizeof(output);
    iconv_t conversion = iconv_open("UTF-16LE", "UTF-8");
    if (conversion == (iconv_t)-1)
        return 1;
    size_t converted = iconv(conversion, &in, &in_left, &out, &out_left);
    if (iconv_close(conversion) != 0 || converted == (size_t)-1 || in_left != 0 ||
        sizeof(output) - out_left != sizeof(expected) || memcmp(output, expected, sizeof(expected)) != 0)
        return 2;

    char invalid[] = "\xff";
    in = invalid;
    out = output;
    in_left = 1;
    out_left = sizeof(output);
    conversion = iconv_open("UTF-16LE", "UTF-8");
    if (conversion == (iconv_t)-1)
        return 3;
    converted = iconv(conversion, &in, &in_left, &out, &out_left);
    if (iconv_close(conversion) != 0 || converted != (size_t)-1 ||
        in_left != 1 || out_left != sizeof(output))
        return 4;

    if (libssh2_init(0) != 0)
        return 5;
    LIBSSH2_SESSION *session = libssh2_session_init_ex(NULL, NULL, NULL, NULL);
    if (!session)
        return 6;
    int passed = supports(session, LIBSSH2_METHOD_KEX, "curve25519-sha256") &&
                 supports(session, LIBSSH2_METHOD_CRYPT_CS, "aes128-ctr") &&
                 supports(session, LIBSSH2_METHOD_COMP_CS, "none");
    if (libssh2_session_flag(session, LIBSSH2_FLAG_COMPRESS, 1) != 0 ||
        !supports(session, LIBSSH2_METHOD_COMP_CS, "zlib@openssh.com"))
        passed = 0;
    if (libssh2_session_free(session) != 0)
        passed = 0;
    libssh2_exit();
    if (!passed)
        return 7;
    puts("native-text-ssh-api-ready");
    fflush(stdout);
    return getchar() == EOF ? 0 : 8;
}

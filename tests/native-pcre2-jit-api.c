#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void fail(const char *message, int code)
{
    fprintf(stderr, "%s: %d\n", message, code);
    exit(1);
}

int main(int argc, char **argv)
{
    static const PCRE2_SPTR pattern =
        (PCRE2_SPTR)"(*UTF)(?<token>lambda-\\x{03bb}\\x{4e2d})-[0-9]{6}";
    static const PCRE2_SPTR subject =
        (PCRE2_SPTR)"prefix lambda-\xce\xbb\xe4\xb8\xad-704810 suffix";
    int unicode = 0;
    int jit = 0;
    int error = 0;
    PCRE2_SIZE offset = 0;

    if (argc != 2)
        return 2;
    if (pcre2_config(PCRE2_CONFIG_UNICODE, &unicode) != 0 || unicode != 1)
        fail("PCRE2 Unicode support unavailable", unicode);
    if (pcre2_config(PCRE2_CONFIG_JIT, &jit) != 0 || jit != 1)
        fail("PCRE2 JIT support unavailable", jit);

    pcre2_code *code = pcre2_compile(
        pattern, PCRE2_ZERO_TERMINATED, PCRE2_UTF | PCRE2_UCP,
        &error, &offset, NULL);
    if (code == NULL)
        fail("PCRE2 compile failed", error);
    error = pcre2_jit_compile(code, PCRE2_JIT_COMPLETE);
    if (error != 0)
        fail("PCRE2 JIT compile failed", error);

    pcre2_match_data *match = pcre2_match_data_create_from_pattern(code, NULL);
    if (match == NULL)
        fail("PCRE2 match-data allocation failed", 0);
    int interpreted = pcre2_match(
        code, subject, strlen((const char *)subject), 0, 0, match, NULL);
    int compiled = pcre2_jit_match(
        code, subject, strlen((const char *)subject), 0, 0, match, NULL);
    if (interpreted < 2 || compiled != interpreted)
        fail("PCRE2 interpreted/JIT match mismatch", compiled);

    FILE *output = fopen(argv[1], "wb");
    if (output == NULL)
        fail("Cannot create API result", 0);
    fprintf(
        output,
        "{\"passed\":true,\"unicode\":%d,\"jit\":%d,"
        "\"interpreted_matches\":%d,\"jit_matches\":%d}\n",
        unicode, jit, interpreted, compiled);
    if (fclose(output) != 0)
        fail("Cannot close API result", 0);

    pcre2_match_data_free(match);
    pcre2_code_free(code);
    return 0;
}

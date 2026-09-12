#define PCRE2_CODE_UNIT_WIDTH 0
#include <pcre2.h>
#include <pcre2posix.h>

#include <stdio.h>
#include <stdlib.h>

static void fail(const char *message, int code)
{
    fprintf(stderr, "%s: %d\n", message, code);
    exit(1);
}

static int test_width8(void)
{
    static const PCRE2_UCHAR8 pattern[] =
        "(*UTF)(?<token>lambda-\\x{03bb}\\x{4e2d})-[0-9]{6}";
    static const PCRE2_UCHAR8 subject[] =
        "prefix lambda-\xce\xbb\xe4\xb8\xad-704810 suffix";
    static const PCRE2_UCHAR8 nonmatch[] = "lambda-missing";
    static const PCRE2_UCHAR8 invalid[] = "(";
    PCRE2_SIZE offset = 0;
    int error = 0;
    int interpreted;
    int compiled;
    int rejected;

    pcre2_code_8 *code = pcre2_compile_8(
        pattern, PCRE2_ZERO_TERMINATED, PCRE2_UTF | PCRE2_UCP,
        &error, &offset, NULL);
    if (code == NULL)
        fail("PCRE2 8-bit compile failed", error);
    if (pcre2_jit_compile_8(code, PCRE2_JIT_COMPLETE) != 0)
        fail("PCRE2 8-bit JIT compile failed", 0);

    pcre2_match_data_8 *match =
        pcre2_match_data_create_from_pattern_8(code, NULL);
    if (match == NULL)
        fail("PCRE2 8-bit match-data allocation failed", 0);
    interpreted = pcre2_match_8(
        code, subject, sizeof(subject) - 1, 0, 0, match, NULL);
    compiled = pcre2_jit_match_8(
        code, subject, sizeof(subject) - 1, 0, 0, match, NULL);
    if (interpreted < 2 || compiled != interpreted)
        fail("PCRE2 8-bit interpreted/JIT mismatch", compiled);
    if (pcre2_jit_match_8(
            code, nonmatch, sizeof(nonmatch) - 1, 0, 0, match, NULL) !=
        PCRE2_ERROR_NOMATCH)
        fail("PCRE2 8-bit nonmatch failed", 0);

    rejected = pcre2_compile_8(
        invalid, PCRE2_ZERO_TERMINATED, 0, &error, &offset, NULL) == NULL;
    if (!rejected)
        fail("PCRE2 8-bit invalid pattern was accepted", 0);

    pcre2_match_data_free_8(match);
    pcre2_code_free_8(code);
    pcre2_jit_free_unused_memory_8(NULL);
    return interpreted;
}

static int test_width16(void)
{
    static const PCRE2_UCHAR16 pattern[] = {
        '(', '?', '<', 't', 'o', 'k', 'e', 'n', '>', 'l', 'a', 'm', 'b',
        'd', 'a', '-', '\\', 'x', '{', '0', '3', 'b', 'b', '}', '\\', 'x',
        '{', '4', 'e', '2', 'd', '}', ')', '-', '[', '0', '-', '9', ']',
        '{', '6', '}', 0
    };
    static const PCRE2_UCHAR16 subject[] = {
        'p', 'r', 'e', 'f', 'i', 'x', ' ', 'l', 'a', 'm', 'b', 'd', 'a',
        '-', 0x03bb, 0x4e2d, '-', '7', '0', '4', '8', '1', '0', ' ', 's',
        'u', 'f', 'f', 'i', 'x', 0
    };
    static const PCRE2_UCHAR16 nonmatch[] = {
        'l', 'a', 'm', 'b', 'd', 'a', '-', 'm', 'i', 's', 's', 'i', 'n',
        'g', 0
    };
    static const PCRE2_UCHAR16 invalid[] = {'(', 0};
    PCRE2_SIZE offset = 0;
    int error = 0;
    int interpreted;
    int compiled;
    int rejected;

    pcre2_code_16 *code = pcre2_compile_16(
        pattern, PCRE2_ZERO_TERMINATED, PCRE2_UTF | PCRE2_UCP,
        &error, &offset, NULL);
    if (code == NULL)
        fail("PCRE2 16-bit compile failed", error);
    if (pcre2_jit_compile_16(code, PCRE2_JIT_COMPLETE) != 0)
        fail("PCRE2 16-bit JIT compile failed", 0);

    pcre2_match_data_16 *match =
        pcre2_match_data_create_from_pattern_16(code, NULL);
    if (match == NULL)
        fail("PCRE2 16-bit match-data allocation failed", 0);
    interpreted = pcre2_match_16(
        code, subject, sizeof(subject) / sizeof(subject[0]) - 1,
        0, 0, match, NULL);
    compiled = pcre2_jit_match_16(
        code, subject, sizeof(subject) / sizeof(subject[0]) - 1,
        0, 0, match, NULL);
    if (interpreted < 2 || compiled != interpreted)
        fail("PCRE2 16-bit interpreted/JIT mismatch", compiled);
    if (pcre2_jit_match_16(
            code, nonmatch, sizeof(nonmatch) / sizeof(nonmatch[0]) - 1,
            0, 0, match, NULL) !=
        PCRE2_ERROR_NOMATCH)
        fail("PCRE2 16-bit nonmatch failed", 0);

    rejected = pcre2_compile_16(
        invalid, PCRE2_ZERO_TERMINATED, 0, &error, &offset, NULL) == NULL;
    if (!rejected)
        fail("PCRE2 16-bit invalid pattern was accepted", 0);

    pcre2_match_data_free_16(match);
    pcre2_code_free_16(code);
    pcre2_jit_free_unused_memory_16(NULL);
    return interpreted;
}

static int test_width32(void)
{
    static const PCRE2_UCHAR32 pattern[] = {
        '(', '?', '<', 't', 'o', 'k', 'e', 'n', '>', 'l', 'a', 'm', 'b',
        'd', 'a', '-', '\\', 'x', '{', '0', '3', 'b', 'b', '}', '\\', 'x',
        '{', '4', 'e', '2', 'd', '}', ')', '-', '[', '0', '-', '9', ']',
        '{', '6', '}', 0
    };
    static const PCRE2_UCHAR32 subject[] = {
        'p', 'r', 'e', 'f', 'i', 'x', ' ', 'l', 'a', 'm', 'b', 'd', 'a',
        '-', 0x03bb, 0x4e2d, '-', '7', '0', '4', '8', '1', '0', ' ', 's',
        'u', 'f', 'f', 'i', 'x', 0
    };
    static const PCRE2_UCHAR32 nonmatch[] = {
        'l', 'a', 'm', 'b', 'd', 'a', '-', 'm', 'i', 's', 's', 'i', 'n',
        'g', 0
    };
    static const PCRE2_UCHAR32 invalid[] = {'(', 0};
    PCRE2_SIZE offset = 0;
    int error = 0;
    int interpreted;
    int compiled;
    int rejected;

    pcre2_code_32 *code = pcre2_compile_32(
        pattern, PCRE2_ZERO_TERMINATED, PCRE2_UTF | PCRE2_UCP,
        &error, &offset, NULL);
    if (code == NULL)
        fail("PCRE2 32-bit compile failed", error);
    if (pcre2_jit_compile_32(code, PCRE2_JIT_COMPLETE) != 0)
        fail("PCRE2 32-bit JIT compile failed", 0);

    pcre2_match_data_32 *match =
        pcre2_match_data_create_from_pattern_32(code, NULL);
    if (match == NULL)
        fail("PCRE2 32-bit match-data allocation failed", 0);
    interpreted = pcre2_match_32(
        code, subject, sizeof(subject) / sizeof(subject[0]) - 1,
        0, 0, match, NULL);
    compiled = pcre2_jit_match_32(
        code, subject, sizeof(subject) / sizeof(subject[0]) - 1,
        0, 0, match, NULL);
    if (interpreted < 2 || compiled != interpreted)
        fail("PCRE2 32-bit interpreted/JIT mismatch", compiled);
    if (pcre2_jit_match_32(
            code, nonmatch, sizeof(nonmatch) / sizeof(nonmatch[0]) - 1,
            0, 0, match, NULL) !=
        PCRE2_ERROR_NOMATCH)
        fail("PCRE2 32-bit nonmatch failed", 0);

    rejected = pcre2_compile_32(
        invalid, PCRE2_ZERO_TERMINATED, 0, &error, &offset, NULL) == NULL;
    if (!rejected)
        fail("PCRE2 32-bit invalid pattern was accepted", 0);

    pcre2_match_data_free_32(match);
    pcre2_code_free_32(code);
    pcre2_jit_free_unused_memory_32(NULL);
    return interpreted;
}

static int test_posix(void)
{
    regex_t expression;
    regmatch_t matches[2];
    int positive;
    int nonmatch;
    int invalid;

    if (regcomp(&expression, "lambda-([0-9]+)", REG_EXTENDED) != 0)
        fail("PCRE2 POSIX compile failed", 0);
    positive = regexec(&expression, "prefix lambda-704810 suffix", 2, matches, 0);
    nonmatch = regexec(&expression, "lambda-missing", 2, matches, 0);
    regfree(&expression);
    invalid = regcomp(&expression, "(", REG_EXTENDED);
    if (positive != 0 || nonmatch != REG_NOMATCH || invalid == 0)
        fail("PCRE2 POSIX behavior failed", positive);
    return 1;
}

int main(int argc, char **argv)
{
    int unicode = 0;
    int jit = 0;
    int newline = 0;
    int width8;
    int width16;
    int width32;
    int posix;
    FILE *output;

    if (argc != 2)
        return 2;
    if (pcre2_config_8(PCRE2_CONFIG_UNICODE, &unicode) != 0 || unicode != 1)
        fail("PCRE2 Unicode support unavailable", unicode);
    if (pcre2_config_8(PCRE2_CONFIG_JIT, &jit) != 0 || jit != 1)
        fail("PCRE2 JIT support unavailable", jit);
    if (pcre2_config_8(PCRE2_CONFIG_NEWLINE, &newline) != 0 ||
        newline != PCRE2_NEWLINE_ANYCRLF)
        fail("PCRE2 ANYCRLF default unavailable", newline);

    width8 = test_width8();
    width16 = test_width16();
    width32 = test_width32();
    posix = test_posix();

    output = fopen(argv[1], "wb");
    if (output == NULL)
        fail("Cannot create all-width API result", 0);
    fprintf(
        output,
        "{\"passed\":true,\"unicode\":%d,\"jit\":%d,\"newline\":%d,"
        "\"width8_matches\":%d,\"width16_matches\":%d,"
        "\"width32_matches\":%d,\"posix\":%d,"
        "\"positive\":true,\"nonmatch\":true,\"invalid_pattern\":true}\n",
        unicode, jit, newline, width8, width16, width32, posix);
    if (fclose(output) != 0)
        fail("Cannot close all-width API result", 0);
    return 0;
}

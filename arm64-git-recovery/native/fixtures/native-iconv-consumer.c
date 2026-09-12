#include <errno.h>
#include <iconv.h>
#include <localcharset.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <windows.h>

int main(int argc, char **argv)
{
    char utf8[] = {'n', 'a', (char)0xce, (char)0xbb};
    const unsigned char expected[] = {'n', 0, 'a', 0, 0xbb, 3};
    char utf16[32], roundtrip[32], invalid[] = {(char)0xff}, path[4096];
    char *input = utf8, *output = utf16;
    size_t input_left = sizeof(utf8), output_left = sizeof(utf16);
    iconv_t conversion = iconv_open("UTF-16LE", "UTF-8");
    FILE *stream;
    if (argc != 2 || conversion == (iconv_t)-1)
        return 2;
    if (iconv(conversion, &input, &input_left, &output, &output_left) == (size_t)-1 ||
        input_left || sizeof(utf16) - output_left != sizeof(expected) ||
        memcmp(utf16, expected, sizeof(expected)) || iconv_close(conversion))
        return 3;
    conversion = iconv_open("UTF-8", "UTF-16LE");
    input = utf16;
    input_left = sizeof(expected);
    output = roundtrip;
    output_left = sizeof(roundtrip);
    if (conversion == (iconv_t)-1 ||
        iconv(conversion, &input, &input_left, &output, &output_left) == (size_t)-1 ||
        input_left || sizeof(roundtrip) - output_left != sizeof(utf8) ||
        memcmp(roundtrip, utf8, sizeof(utf8)) || iconv_close(conversion))
        return 4;
    conversion = iconv_open("UTF-16LE", "UTF-8");
    input = invalid;
    input_left = sizeof(invalid);
    output = utf16;
    output_left = sizeof(utf16);
    errno = 0;
    if (conversion == (iconv_t)-1 ||
        iconv(conversion, &input, &input_left, &output, &output_left) != (size_t)-1 ||
        errno != EILSEQ || input_left != sizeof(invalid) || iconv_close(conversion))
        return 5;
    errno = 0;
    if (iconv_open("NO-SUCH-ENCODING", "UTF-8") != (iconv_t)-1 || errno != EINVAL)
        return 6;
    const char *charset = locale_charset();
    if (!charset || !*charset)
        return 7;
    if (snprintf(path, sizeof(path), "%s/ready", argv[1]) >= (int)sizeof(path))
        return 8;
    stream = fopen(path, "w");
    if (!stream || fprintf(stream, "%lu\n", (unsigned long)GetCurrentProcessId()) < 0 || fclose(stream))
        return 9;
    if (snprintf(path, sizeof(path), "%s/continue", argv[1]) >= (int)sizeof(path))
        return 10;
    for (int i = 0; i < 3000; ++i) {
        if (access(path, F_OK) == 0) {
            puts("native-iconv-consumer-passed");
            return 0;
        }
        usleep(10000);
    }
    return 11;
}

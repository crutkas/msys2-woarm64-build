#include <errno.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#ifdef PROBE_ICONV
#include <iconv.h>
#include <localcharset.h>
#else
#include <libintl.h>
#endif

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "native-nls:%d: %s (errno=%d)\n", __LINE__, #condition, errno); \
        return 1; \
    } \
} while (0)

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    CHECK(sizeof(long) == 8 && sizeof(void *) == 8);
    CHECK(setlocale(LC_ALL, "C.UTF-8") != NULL);
    FILE *ready = fopen("ready", "wb");
    CHECK(ready != NULL);
    CHECK(fclose(ready) == 0);
    time_t end = time(NULL) + 30;
    while (access("continue", F_OK) != 0 && time(NULL) < end)
        usleep(50000);
    CHECK(access("continue", F_OK) == 0);
#ifdef PROBE_ICONV
    CHECK(_LIBICONV_VERSION == 0x0113 && _libiconv_version == 0x0113);
    CHECK(strcmp(locale_charset(), "UTF-8") == 0);
    char input[] = "A\316\273\344\270\255";
    const unsigned char expected[] = {0x41, 0x00, 0xbb, 0x03, 0x2d, 0x4e};
    char output[32] = {0};
    char *in = input, *out = output;
    size_t left = sizeof(input) - 1, available = sizeof(output);
    iconv_t converter = iconv_open("UTF-16LE", "UTF-8");
    CHECK(converter != (iconv_t)-1);
    CHECK(iconv(converter, &in, &left, &out, &available) == 0);
    CHECK(left == 0 && sizeof(output) - available == sizeof(expected));
    CHECK(memcmp(output, expected, sizeof(expected)) == 0);
    CHECK(iconv_close(converter) == 0);
    char roundtrip[32] = {0};
    converter = iconv_open("UTF-8", "UTF-16LE");
    CHECK(converter != (iconv_t)-1);
    in = output; left = sizeof(expected); out = roundtrip; available = sizeof(roundtrip);
    CHECK(iconv(converter, &in, &left, &out, &available) == 0);
    CHECK(left == 0 && strcmp(roundtrip, input) == 0);
    CHECK(iconv_close(converter) == 0);
    converter = iconv_open("UTF-8", "CP1133");
    CHECK(converter != (iconv_t)-1);
    CHECK(iconv_close(converter) == 0);
    converter = iconv_open("UTF-16LE", "UTF-8");
    CHECK(converter != (iconv_t)-1);
    char invalid[] = "\377";
    in = invalid; left = 1; out = output; available = sizeof(output); errno = 0;
    CHECK(iconv(converter, &in, &left, &out, &available) == (size_t)-1);
    CHECK(errno == EILSEQ && left == 1);
    CHECK(iconv_close(converter) == 0);
#else
    const char *directory = getenv("NATIVE_NLS_LOCALE_DIR");
    CHECK(directory != NULL);
    CHECK(bindtextdomain("native-nls", directory) != NULL);
    CHECK(bind_textdomain_codeset("native-nls", "UTF-8") != NULL);
    CHECK(textdomain("native-nls") != NULL);
    CHECK(strcmp(gettext("native hello"), "bonjour natif") == 0);
    CHECK(strcmp(ngettext("one glyph", "many glyphs", 1), "un signe") == 0);
    CHECK(strcmp(ngettext("one glyph", "many glyphs", 3), "plusieurs signes") == 0);
    CHECK(strcmp(dgettext("missing-domain", "native hello"), "native hello") == 0);
    CHECK(bind_textdomain_codeset("native-nls", "ISO-8859-1") != NULL);
    CHECK(strcmp(gettext("coffee"), "caf\351") == 0);
    CHECK(bind_textdomain_codeset("native-nls", "UTF-8") != NULL);
    CHECK(strcmp(gettext("coffee"), "caf\303\251") == 0);
#endif
    FILE *report = fopen(argv[1], "wb");
    CHECK(report != NULL);
    CHECK(fprintf(report, "{\"passed\":true,\"lp64\":true,\"real_api\":true}\n") > 0);
    CHECK(fclose(report) == 0);
    return 0;
}

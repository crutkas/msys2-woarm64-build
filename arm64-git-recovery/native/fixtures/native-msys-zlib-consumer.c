#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <windows.h>
#include <zlib.h>

_Static_assert(sizeof(uLong) == 8, "MSYS zlib must use the LP64 target ABI");

int main(int argc, char **argv)
{
    unsigned char original[4096], compressed[8192], restored[4096];
    uLongf compressed_size = sizeof(compressed), restored_size = sizeof(restored);
    char path[4096];
    FILE *stream;
    if (argc != 2)
        return 2;
    for (unsigned int i = 0; i < sizeof(original); ++i)
        original[i] = (unsigned char)(i * 37);
    if (compress2(compressed, &compressed_size, original, sizeof(original), Z_BEST_COMPRESSION) != Z_OK ||
        uncompress(restored, &restored_size, compressed, compressed_size) != Z_OK ||
        restored_size != sizeof(original) || memcmp(original, restored, sizeof(original)))
        return 3;
    compressed[0] ^= 0xff;
    restored_size = sizeof(restored);
    if (uncompress(restored, &restored_size, compressed, compressed_size) != Z_DATA_ERROR)
        return 4;
    if (snprintf(path, sizeof(path), "%s/roundtrip.gz", argv[1]) >= (int)sizeof(path))
        return 5;
    gzFile gzip = gzopen(path, "wb");
    if (!gzip || gzwrite(gzip, original, sizeof(original)) != sizeof(original) || gzclose(gzip) != Z_OK)
        return 6;
    gzip = gzopen(path, "rb");
    if (!gzip || gzread(gzip, restored, sizeof(restored)) != sizeof(restored) ||
        memcmp(original, restored, sizeof(original)) || gzclose(gzip) != Z_OK)
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
            puts("native-zlib-consumer-passed");
            return 0;
        }
        usleep(10000);
    }
    return 11;
}

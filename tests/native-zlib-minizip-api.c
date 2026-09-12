#include <stdio.h>
#include <string.h>
#include <zlib.h>
#include <minizip/zip.h>
#include <minizip/unzip.h>

#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "native-zlib-minizip check failed at line %d\n", __LINE__); \
    return 1; } } while (0)

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 4, "MinGW ARM64 LLP64 required");

int main(void)
{
    unsigned char input[4096], packed[8192], restored[4096];
    uLongf packed_size = sizeof(packed), restored_size = sizeof(restored);
    const int methods[] = {Z_DEFLATED, 12}; /* ZIP method 12 is bzip2. */
    const char *names[] = {"deflate.bin", "bzip2.bin"};
    zipFile archive;
    unzFile reader;
    unsigned int i;

    for (i = 0; i < sizeof(input); i++)
        input[i] = (unsigned char)((i * 73 + 19) % 256);
    REQUIRE(strcmp(zlibVersion(), ZLIB_VERSION) == 0);
    REQUIRE(compress2(packed, &packed_size, input, sizeof(input), Z_BEST_COMPRESSION) == Z_OK);
    REQUIRE(uncompress(restored, &restored_size, packed, packed_size) == Z_OK);
    REQUIRE(restored_size == sizeof(input) && memcmp(input, restored, sizeof(input)) == 0);
    packed[0] ^= 255;
    restored_size = sizeof(restored);
    REQUIRE(uncompress(restored, &restored_size, packed, packed_size) == Z_DATA_ERROR);

    archive = zipOpen64("native-minizip.zip", APPEND_STATUS_CREATE);
    REQUIRE(archive != NULL);
    for (i = 0; i < 2; i++) {
        REQUIRE(zipOpenNewFileInZip64(archive, names[i], NULL, NULL, 0, NULL, 0, NULL,
                                     methods[i], Z_BEST_COMPRESSION, 1) == ZIP_OK);
        REQUIRE(zipWriteInFileInZip(archive, input, sizeof(input)) == ZIP_OK);
        REQUIRE(zipCloseFileInZip(archive) == ZIP_OK);
    }
    REQUIRE(zipClose(archive, NULL) == ZIP_OK);
    reader = unzOpen64("native-minizip.zip");
    REQUIRE(reader != NULL && unzGoToFirstFile(reader) == UNZ_OK);
    for (i = 0; i < 2; i++) {
        REQUIRE(unzOpenCurrentFile(reader) == UNZ_OK);
        REQUIRE(unzReadCurrentFile(reader, restored, sizeof(restored)) == sizeof(input));
        REQUIRE(memcmp(input, restored, sizeof(input)) == 0);
        REQUIRE(unzCloseCurrentFile(reader) == UNZ_OK);
        if (i == 0)
            REQUIRE(unzGoToNextFile(reader) == UNZ_OK);
    }
    REQUIRE(unzClose(reader) == UNZ_OK);
    puts("native-zlib-minizip-api-ready");
    fflush(stdout);
    REQUIRE(getchar() == '!');
    puts("native-zlib-minizip-api-passed");
    return 0;
}

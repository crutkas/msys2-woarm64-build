#include <winsock2.h>
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(LEAF_BROTLI)
#include <brotli/encode.h>
#include <brotli/decode.h>
#elif defined(LEAF_CARES)
#include <ares.h>
#elif defined(LEAF_ZSTD)
#include <zstd.h>
#elif defined(LEAF_NGHTTP2)
#include <nghttp2/nghttp2.h>
#else
#error A leaf must be selected
#endif

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static int binding(const char *symbol, const void *address) {
    HMODULE module = NULL;
    char path[32768];
    CHECK(GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCSTR)address, &module));
    CHECK(GetModuleFileNameA(module, path, sizeof(path)) > 0);
    printf("BINDING\t%s\t%s\n", symbol, path);
    return 0;
}

#if defined(LEAF_BROTLI) || defined(LEAF_ZSTD)
static void payload(unsigned char *data, size_t size) {
    size_t i;
    for (i = 0; i < size; ++i)
        data[i] = (unsigned char)((i * 29 + i / 131) & 255);
}
#endif

static int exercise(void) {
#if defined(LEAF_BROTLI)
    unsigned char input[8192], compressed[16384], decoded[8192];
    const unsigned char invalid[] = {255, 255, 255, 255};
    size_t compressed_size = sizeof(compressed), decoded_size = sizeof(decoded);
    payload(input, sizeof(input));
    CHECK(BrotliEncoderCompress(5, BROTLI_DEFAULT_WINDOW, BROTLI_MODE_GENERIC,
                               sizeof(input), input, &compressed_size, compressed));
    CHECK(compressed_size > 0 && compressed_size < sizeof(input));
    CHECK(BrotliDecoderDecompress(compressed_size, compressed, &decoded_size, decoded)
          == BROTLI_DECODER_RESULT_SUCCESS);
    CHECK(decoded_size == sizeof(input) && !memcmp(input, decoded, sizeof(input)));
    puts("CASE\tcompression-roundtrip-bytes");
    decoded_size = 1;
    CHECK(BrotliDecoderDecompress(compressed_size, compressed, &decoded_size, decoded)
          != BROTLI_DECODER_RESULT_SUCCESS);
    puts("CASE\tundersized-destination-rejected");
    decoded_size = sizeof(decoded);
    CHECK(BrotliDecoderDecompress(sizeof(invalid), invalid, &decoded_size, decoded)
          == BROTLI_DECODER_RESULT_ERROR);
    puts("CASE\tmalformed-stream-rejected");
    CHECK(binding("BrotliEncoderCompress", (const void *)BrotliEncoderCompress) == 0);
    CHECK(binding("BrotliDecoderDecompress", (const void *)BrotliDecoderDecompress) == 0);
#elif defined(LEAF_ZSTD)
    unsigned char input[8192], compressed[16384], decoded[8192];
    const unsigned char invalid[] = {255, 255, 255, 255};
    size_t compressed_size, decoded_size;
    payload(input, sizeof(input));
    compressed_size = ZSTD_compress(compressed, sizeof(compressed), input, sizeof(input), 3);
    CHECK(!ZSTD_isError(compressed_size) && compressed_size < sizeof(input));
    decoded_size = ZSTD_decompress(decoded, sizeof(decoded), compressed, compressed_size);
    CHECK(!ZSTD_isError(decoded_size) && decoded_size == sizeof(input));
    CHECK(!memcmp(input, decoded, sizeof(input)));
    puts("CASE\tcompression-roundtrip-bytes");
    CHECK(ZSTD_isError(ZSTD_decompress(decoded, 1, compressed, compressed_size)));
    puts("CASE\tundersized-destination-rejected");
    CHECK(ZSTD_isError(ZSTD_decompress(decoded, sizeof(decoded), invalid, sizeof(invalid))));
    puts("CASE\tmalformed-stream-rejected");
    CHECK(binding("ZSTD_compress", (const void *)ZSTD_compress) == 0);
    CHECK(binding("ZSTD_decompress", (const void *)ZSTD_decompress) == 0);
#elif defined(LEAF_CARES)
    ares_channel channel = NULL;
    unsigned char *query = NULL;
    unsigned char address[16];
    int query_size = 0;
    char *name = NULL;
    long name_size = 0;
    char invalid_name[80];
    CHECK(ares_library_init(ARES_LIB_INIT_ALL) == ARES_SUCCESS);
    CHECK(ares_init(&channel) == ARES_SUCCESS);
    CHECK(ares_inet_pton(AF_INET, "192.0.2.7", address) == 1);
    CHECK(address[0] == 192 && address[1] == 0 && address[2] == 2 && address[3] == 7);
    CHECK(ares_inet_pton(AF_INET6, "2001:db8::1", address) == 1);
    CHECK(address[0] == 0x20 && address[1] == 1 && address[15] == 1);
    CHECK(ares_inet_pton(AF_INET, "999.0.0.1", address) == 0);
    puts("CASE\tipv4-ipv6-positive-invalid");
    CHECK(ares_create_query("example.com", 1, 1, 0x1234, 1, &query, &query_size, 0)
          == ARES_SUCCESS);
    CHECK(query_size == 29 && query[0] == 0x12 && query[1] == 0x34);
    CHECK(ares_expand_name(query + 12, query, query_size, &name, &name_size) == ARES_SUCCESS);
    CHECK(!strcmp(name, "example.com") && name_size == 13);
    ares_free_string(name);
    name = NULL;
    CHECK(ares_expand_name(query + 12, query, 13, &name, &name_size) == ARES_EBADNAME);
    ares_free_string(query);
    query = NULL;
    puts("CASE\tdns-query-encode-decode-truncation");
    memset(invalid_name, 'a', 64);
    strcpy(invalid_name + 64, ".example");
    CHECK(ares_create_query(invalid_name, 1, 1, 0, 1, &query, &query_size, 0) == ARES_EBADNAME);
    puts("CASE\toverlong-dns-label-rejected");
    ares_destroy(channel);
    ares_library_cleanup();
    CHECK(binding("ares_create_query", (const void *)ares_create_query) == 0);
    CHECK(binding("ares_inet_pton", (const void *)ares_inet_pton) == 0);
#elif defined(LEAF_NGHTTP2)
    nghttp2_hd_deflater *deflater = NULL;
    nghttp2_hd_inflater *inflater = NULL;
    nghttp2_session_callbacks *callbacks = NULL;
    nghttp2_session *session = NULL;
    nghttp2_nv input[] = {
        {(uint8_t *)":method", (uint8_t *)"GET", 7, 3, NGHTTP2_NV_FLAG_NONE},
        {(uint8_t *)":path", (uint8_t *)"/arm64", 5, 6, NGHTTP2_NV_FLAG_NONE}
    };
    uint8_t compressed[256];
    ssize_t size, consumed;
    size_t offset = 0, emitted = 0;
    int flags = 0;
    CHECK(nghttp2_hd_deflate_new(&deflater, 4096) == 0);
    CHECK(nghttp2_hd_inflate_new(&inflater) == 0);
    size = nghttp2_hd_deflate_hd(deflater, compressed, sizeof(compressed), input, 2);
    CHECK(size > 0);
    while (!(flags & NGHTTP2_HD_INFLATE_FINAL)) {
        nghttp2_nv output;
        consumed = nghttp2_hd_inflate_hd2(inflater, &output, &flags, compressed + offset,
                                         (size_t)size - offset, 1);
        CHECK(consumed >= 0);
        offset += (size_t)consumed;
        if (flags & NGHTTP2_HD_INFLATE_EMIT) {
            CHECK(emitted < 2);
            CHECK(output.namelen == input[emitted].namelen && output.valuelen == input[emitted].valuelen);
            CHECK(!memcmp(output.name, input[emitted].name, output.namelen));
            CHECK(!memcmp(output.value, input[emitted].value, output.valuelen));
            emitted++;
        }
        CHECK(consumed || (flags & (NGHTTP2_HD_INFLATE_EMIT | NGHTTP2_HD_INFLATE_FINAL)));
    }
    CHECK(offset == (size_t)size && emitted == 2);
    CHECK(nghttp2_hd_inflate_end_headers(inflater) == 0);
    puts("CASE\thpack-header-roundtrip-bytes");
    nghttp2_hd_inflate_del(inflater);
    inflater = NULL;
    CHECK(nghttp2_hd_inflate_new(&inflater) == 0);
    {
        nghttp2_nv output;
        const uint8_t invalid[] = {0x80};
        CHECK(nghttp2_hd_inflate_hd2(inflater, &output, &flags, invalid, sizeof(invalid), 1)
              == NGHTTP2_ERR_HEADER_COMP);
    }
    puts("CASE\tinvalid-hpack-index-rejected");
    CHECK(nghttp2_session_callbacks_new(&callbacks) == 0);
    CHECK(nghttp2_session_client_new(&session, callbacks, NULL) == 0);
    CHECK(nghttp2_submit_window_update(session, NGHTTP2_FLAG_NONE, 0, 1) == 0);
    CHECK(nghttp2_submit_rst_stream(session, NGHTTP2_FLAG_NONE, 0, NGHTTP2_CANCEL)
          == NGHTTP2_ERR_INVALID_ARGUMENT);
    puts("CASE\tsession-positive-invalid-stream");
    nghttp2_session_del(session);
    nghttp2_session_callbacks_del(callbacks);
    nghttp2_hd_inflate_del(inflater);
    nghttp2_hd_deflate_del(deflater);
    CHECK(binding("nghttp2_hd_deflate_hd", (const void *)nghttp2_hd_deflate_hd) == 0);
    CHECK(binding("nghttp2_hd_inflate_hd2", (const void *)nghttp2_hd_inflate_hd2) == 0);
#endif
    return 0;
}

int main(int argc, char **argv) {
    int result = exercise();
    if (result)
        return result;
    if (argc == 2 && !strcmp(argv[1], "--negative-control")) {
        fputs("intentional failing expectation\n", stderr);
        return 91;
    }
    puts("READY");
    fflush(stdout);
    if (argc == 2 && !strcmp(argv[1], "--hold"))
        (void)getchar();
    puts("PASS");
    return 0;
}

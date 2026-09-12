#define main display_cells_regression_main
#include "../patches/libedit-20240808-display-cells-regression.c"
#undef main

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;
    puts("curses-cpp-ready");
    fflush(stdout);
    if (getchar() != '\n')
        return 3;
    size_t length = strlen(argv[1]) + sizeof(".transcript");
    char *transcript = malloc(length);
    if (!transcript)
        return 4;
    snprintf(transcript, length, "%s.transcript", argv[1]);
    char *arguments[] = {argv[0], transcript, NULL};
    int result = display_cells_regression_main(2, arguments);
    free(transcript);
    if (result)
        return result;
    FILE *report = fopen(argv[1], "wb");
    if (!report)
        return 5;
    int written = fprintf(report,
        "{\"passed\":true,\"mixed_width_cells\":true,\"literal_tags\":true,"
        "\"cjk_fillers\":true,\"wrap_scroll_diff\":true,\"exact_output_bytes\":true}\n");
    if (fclose(report) != 0 || written < 0)
        return 6;
    return 0;
}

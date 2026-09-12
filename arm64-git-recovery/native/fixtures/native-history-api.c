#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <readline/history.h>

int main(int argc, char **argv)
{
    if (argc != 2 || sizeof(long) != 8 || !setlocale(LC_ALL, "C.UTF-8") || MB_CUR_MAX <= 1)
        return 2;
    const char expected[] = "before \316\273";
    using_history();
    add_history("alpha");
    add_history(expected);
    char *expanded = NULL;
    if (history_expand("!!", &expanded) != 1 || !expanded || strcmp(expanded, expected) != 0)
        return 3;
    free(expanded);
    stifle_history(10);
    if (!history_is_stifled() || unstifle_history() != 10 || history_is_stifled())
        return 4;
    if (write_history("standalone-history.txt") != 0)
        return 5;
    clear_history();
    if (read_history("standalone-history.txt") != 0 || history_length != 2)
        return 6;
    HIST_ENTRY *last = history_get(history_base + history_length - 1);
    if (!last || strcmp(last->line, expected) != 0)
        return 7;
    HIST_ENTRY *removed = remove_history(0);
    if (!removed || strcmp(removed->line, "alpha") != 0 || history_length != 1)
        return 8;
    free_history_entry(removed);
    puts("history-api-ready");
    fflush(stdout);
    if (getchar() != '\n')
        return 9;
    FILE *report = fopen(argv[1], "wb");
    if (!report)
        return 10;
    int written = fprintf(report,
        "{\"passed\":true,\"lp64\":true,\"unicode_history\":true,"
        "\"expansion\":true,\"stifle_unstifle\":true,\"file_roundtrip\":true,\"remove\":true}\n");
    if (fclose(report) != 0 || written < 0)
        return 11;
    clear_history();
    return 0;
}

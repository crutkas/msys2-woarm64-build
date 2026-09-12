#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifdef PROBE_READLINE
#include <readline/readline.h>
#include <readline/history.h>
#else
#include <histedit.h>

static wchar_t *prompt(EditLine *editor)
{
    (void)editor;
    return L"\001\033[31m\001\u4e2d\001\033[0m\001 chain-ready> ";
}

static wchar_t *history_prompt(EditLine *editor)
{
    (void)editor;
    return L"\001\033[31m\001\u4e2d\001\033[0m\001 chain-history> ";
}
#endif

int main(int argc, char **argv)
{
    if (argc != 2 || sizeof(void *) != 8 || sizeof(long) != 8 ||
        !setlocale(LC_ALL, "C.UTF-8") || MB_CUR_MAX <= 1)
        return 2;
#ifdef PROBE_READLINE
    const char expected[] = "before \316\273";
#else
    const char expected[] = "before \316\273\344\270\255";
#endif
    int passed = 0;
#ifdef PROBE_READLINE
    using_history();
    add_history("pinned-history");
    char *expanded = NULL;
    if (history_expand("!!", &expanded) != 1 || !expanded ||
        strcmp(expanded, "pinned-history") != 0)
        return 3;
    free(expanded);
    rl_readline_name = "owned-chain-probe";
    char *line = readline("chain-ready> ");
    if (!line || strcmp(line, expected) != 0)
        return 4;
    add_history(line);
    if (write_history("owned-history.txt") != 0)
        return 5;
    free(line);
    line = readline("chain-history> ");
    passed = line && strcmp(line, expected) == 0 && history_length == 2 &&
        rl_readline_version == 0x0803;
    free(line);
    clear_history();
    if (read_history("owned-history.txt") != 0 || history_length != 2)
        return 6;
#else
    HistoryW *hist = history_winit();
    HistEventW event;
    EditLine *editor = el_init("owned-chain-probe", stdin, stdout, stderr);
    if (!hist || !editor || history_w(hist, &event, H_SETSIZE, 20) < 0 ||
        el_wset(editor, EL_EDITOR, L"emacs") != 0 ||
        el_wset(editor, EL_PROMPT_ESC, prompt, L'\001') != 0 ||
        el_wset(editor, EL_HIST, history_w, hist) != 0)
        return 3;
    int count = 0;
    const wchar_t *line = el_wgets(editor, &count);
    if (!line || wcscmp(line, L"before \u03bb\u4e2d\n") != 0 || count != 10 ||
        history_w(hist, &event, H_ENTER, line) < 0 ||
        history_w(hist, &event, H_SAVE, "owned-history.txt") < 0)
        return 4;
    if (el_wset(editor, EL_PROMPT_ESC, history_prompt, L'\001') != 0)
        return 5;
    line = el_wgets(editor, &count);
    passed = line && wcscmp(line, L"before \u03bb\u4e2d\n") == 0 && count == 10;
    el_end(editor);
    history_wend(hist);
    History *narrow = history_init();
    HistEvent narrow_event;
    if (!narrow || history(narrow, &narrow_event, H_SETSIZE, 20) < 0 ||
        history(narrow, &narrow_event, H_ENTER, expected) < 0 ||
        history(narrow, &narrow_event, H_FIRST) < 0 ||
        strcmp(narrow_event.str, expected) != 0)
        return 6;
    history_end(narrow);
#endif
    FILE *report = fopen(argv[1], "wb");
    if (!report)
        return 7;
    int result = fprintf(report,
        "{\"passed\":%s,\"lp64\":true,\"multibyte\":true,"
        "\"pty_edit\":\"before-lambda-backspace\","
        "\"history_recall\":true,\"history_file\":true}\n",
        passed ? "true" : "false");
    if (fclose(report) != 0 || result < 0)
        return 8;
    return passed ? 0 : 9;
}

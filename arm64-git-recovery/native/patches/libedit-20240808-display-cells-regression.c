/*
 * Native MSYS ARM64 white-box regression for the display-cells patch.
 *
 * NOT executed by the code-only port task. Build later with the actual
 * configured libedit source/build include directories and libedit's static
 * archive plus its native terminal-library dependencies. No stubs or header
 * substitutes are used. Compile this fixture and the library with matching
 * DEBUG_REFRESH settings when exercising the debug path.
 *
 * The sole argument is a new transcript path in the observer's owned output
 * directory. The file is created exclusively and retained as evidence.
 * This fixture uses a regular file, never a terminal or a temporary file.
 * A separate PTY exercise must check terminal-visible cursor positioning.
 */
#include "config.h"
#include <sys/types.h>
#include <fcntl.h>
#include <limits.h>
#include <locale.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>
#include <wchar.h>
#include <wctype.h>

#include "el.h"

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "native MSYS LP64");
_Static_assert(sizeof(wchar_t) == 2 && sizeof(wint_t) == 4, "mixed wide ABI");
_Static_assert(sizeof(**((EditLine *)0)->el_display) == sizeof(wint_t),
    "real display cell width");
_Static_assert(sizeof(**((EditLine *)0)->el_vdisplay) == sizeof(wint_t),
    "virtual display cell width");
_Static_assert(EL_LITERAL == UINT32_C(0x80000000), "literal tag bits");
_Static_assert(MB_FILL_CHAR == UINT32_MAX, "filler bits");
_Static_assert(MB_FILL_CHAR != (wint_t)WCHAR_MAX, "filler is not a wchar_t");

#define CHECK(expr) do { \
	if (!(expr)) { \
		fprintf(stderr, "display-cells:%d: %s\n", __LINE__, #expr); \
		exit(EXIT_FAILURE); \
	} \
} while (0)

static wchar_t *
empty_prompt(EditLine *el)
{
	(void)el;
	return L"";
}

static wchar_t *
color_prompt(EditLine *el)
{
	(void)el;
	return L"\001\033[31m\001\u4e2d\001\033[0m\001> ";
}

static void
capability(EditLine *el, const wchar_t *name, const wchar_t *value)
{
	const wchar_t *args[] = { L"settc", name, value, NULL };
	CHECK(terminal_settc(el, 3, args) == 0);
}

static void
plain_capabilities(EditLine *el)
{
	static const wchar_t *names[] = {
		L"ch", L"RI", L"LE", L"UP", L"up", L"ce", L"DC", L"dc",
		L"IC", L"ic", L"im", L"ei", L"ip", L"dm", L"ed"
	};
	size_t i;

	for (i = 0; i < sizeof(names) / sizeof(names[0]); i++)
		capability(el, names[i], L"");
	capability(el, L"pt", L"no");
	capability(el, L"am", L"no");
	capability(el, L"xn", L"no");
}

static void
screen(EditLine *el, int rows, int columns)
{
	int i;

	literal_clear(el);
	CHECK(terminal_change_size(el, rows, columns) == 0);
	CHECK(el->el_terminal.t_size.h == columns);
	CHECK(el->el_terminal.t_size.v == rows);
	CHECK(el->el_display[rows] == NULL);
	CHECK(el->el_vdisplay[rows] == NULL);
	for (i = 0; i < rows; i++) {
		CHECK(el->el_display[i][columns] == 0);
		CHECK(el->el_vdisplay[i][columns] == 0);
	}
	re_clear_display(el);
	el->el_refresh.r_cursor.h = el->el_refresh.r_cursor.v = 0;
	el->el_refresh.r_newcv = 0;
	el->el_prompt.p_pos.h = el->el_prompt.p_pos.v = 0;
	el->el_rprompt.p_pos.h = el->el_rprompt.p_pos.v = 0;
}

static void
input_line(EditLine *el, const wchar_t *text)
{
	size_t n = wcslen(text);

	CHECK(n + 1 <= (size_t)(el->el_line.limit - el->el_line.buffer));
	wmemcpy(el->el_line.buffer, text, n + 1);
	el->el_line.cursor = el->el_line.lastchar = el->el_line.buffer + n;
}

static wint_t
red_literal(EditLine *el)
{
	static const wchar_t text[] = L"\033[31m\001\u4e2d";
	int width = -1;
	wint_t cell = literal_add(el, text, wcschr(text, L'\001'), &width);

	CHECK(width == 2);
	CHECK(cell != MB_FILL_CHAR && (cell & EL_LITERAL) != 0);
	CHECK(strcmp(literal_get(el, cell), "\033[31m\xe4\xb8\xad") == 0);
	return cell;
}

static long
checkpoint(FILE *out)
{
	long offset;

	CHECK(fflush(out) == 0);
	offset = ftell(out);
	CHECK(offset >= 0);
	return offset;
}

static size_t
read_output(FILE *out, long start, char *bytes, size_t capacity)
{
	long end = checkpoint(out);
	size_t n;

	CHECK(end >= start);
	n = (size_t)(end - start);
	CHECK(n < capacity);
	CHECK(fseek(out, start, SEEK_SET) == 0);
	CHECK(fread(bytes, 1, n, out) == n);
	bytes[n] = '\0';
	CHECK(fseek(out, end, SEEK_SET) == 0);
	return n;
}

static void
expect_output(FILE *out, long start, const char *expected)
{
	char bytes[1024];
	size_t n = read_output(out, start, bytes, sizeof(bytes));

	CHECK(n == strlen(expected));
	CHECK(memcmp(bytes, expected, n) == 0);
}

static void
output_paths(EditLine *el, FILE *out)
{
	wint_t *row, tag, endtag;
	static const wchar_t reset[] = L"\033[0m\001X";
	static const char expected[] =
	    "A\xe4\xb8\xad\033[31m\xe4\xb8\xad\033[0mX";
	int width;
	long start;

	screen(el, 3, 24);
	tag = red_literal(el);
	CHECK(tag == EL_LITERAL); /* Low 16 bits zero must not end a line. */
	endtag = literal_add(el, reset, wcschr(reset, L'\001'), &width);
	CHECK(endtag == (EL_LITERAL | (wint_t)1) && width == 1);
	row = el->el_display[0];
	row[0] = 'A';
	row[1] = L'\u4e2d';
	row[2] = MB_FILL_CHAR;
	row[3] = tag;
	row[4] = MB_FILL_CHAR;
	row[5] = endtag;
	row[6] = 0;
	start = checkpoint(out);
	terminal_overwrite(el, row, 6);
	CHECK(el->el_cursor.h == 6);
	expect_output(out, start, expected);

	el->el_cursor.h = 0;
	start = checkpoint(out);
	terminal_move_to_char(el, 6);
	CHECK(el->el_cursor.h == 6);
	expect_output(out, start, expected);
	start = checkpoint(out);
	CHECK(terminal__putc(el, MB_FILL_CHAR) == 0);
	expect_output(out, start, "");

	/* Exercise all three insertion paths, retaining a literal and filler. */
	row[0] = tag;
	row[1] = MB_FILL_CHAR;
	capability(el, L"ic", L"\033[@");
	el->el_cursor.h = 0;
	start = checkpoint(out);
	terminal_insertwrite(el, row, 2);
	CHECK(el->el_cursor.h == 2);
	expect_output(out, start, "\033[@\033[31m\xe4\xb8\xad\033[@");
	capability(el, L"im", L"\033[4h");
	capability(el, L"ei", L"\033[4l");
	el->el_cursor.h = 0;
	start = checkpoint(out);
	terminal_insertwrite(el, row, 2);
	CHECK(el->el_cursor.h == 2);
	expect_output(out, start, "\033[4h\033[31m\xe4\xb8\xad\033[4l");
	capability(el, L"IC", L"\033[%d@");
	el->el_cursor.h = 0;
	start = checkpoint(out);
	terminal_insertwrite(el, row, 2);
	CHECK(el->el_cursor.h == 2);
	expect_output(out, start, "\033[2@\033[31m\xe4\xb8\xad");
	plain_capabilities(el);

	el->el_cursor.h = 0;
	start = checkpoint(out);
	terminal_writec(el, 4);
	CHECK(el->el_cursor.h == 2);
	expect_output(out, start, "^D");
}

static void
wrapping_and_scrolling(EditLine *el, FILE *out)
{
	static const wchar_t literal[] = L"\033[31m\001\u4e2d";
	wint_t *first, *last, tag;
	const wint_t bang = '!';
	long start;
	int i;

	screen(el, 2, 8);
	el->el_refresh.r_cursor.h = 7;
	re_putliteral(el, literal, wcschr(literal, L'\001'));
	CHECK(el->el_vdisplay[0][7] == ' ');
	CHECK(el->el_vdisplay[0][8] == 0);
	CHECK(el->el_vdisplay[1][0] == EL_LITERAL);
	CHECK(el->el_vdisplay[1][1] == MB_FILL_CHAR);
	CHECK(el->el_refresh.r_cursor.h == 2);
	CHECK(el->el_refresh.r_cursor.v == 1);

	screen(el, 2, 8);
	el->el_refresh.r_cursor.h = 7;
	re_putc(el, L'\u4e2d', 1);
	CHECK(el->el_vdisplay[0][7] == ' ');
	CHECK(el->el_vdisplay[1][0] == L'\u4e2d');
	CHECK(el->el_vdisplay[1][1] == MB_FILL_CHAR);
	first = el->el_vdisplay[0];
	last = el->el_vdisplay[1];
	el->el_refresh.r_cursor.h = 7;
	re_putc(el, 'Z', 1);
	CHECK(el->el_vdisplay[0] == last && el->el_vdisplay[1] == first);
	CHECK(el->el_vdisplay[0][1] == MB_FILL_CHAR);
	CHECK(el->el_vdisplay[1][0] == 0);

	screen(el, 2, 8);
	first = el->el_display[0];
	last = el->el_display[1];
	el->el_cursor.h = 6;
	el->el_cursor.v = el->el_refresh.r_oldcv = 1;
	input_line(el, L"\u4e2d");
	start = checkpoint(out);
	re_fastaddc(el);
	expect_output(out, start, "\xe4\xb8\xad\r\n");
	CHECK(el->el_display[0] == last && el->el_display[1] == first);
	CHECK(el->el_display[0][6] == L'\u4e2d');
	CHECK(el->el_display[0][7] == MB_FILL_CHAR);
	for (i = 0; i < 8; i++)
		CHECK(el->el_display[1][i] == ' ');
	CHECK(el->el_display[1][8] == 0);
	CHECK(el->el_cursor.h == 0 && el->el_cursor.v == 1);

	screen(el, 2, 4);
	tag = red_literal(el);
	el->el_display[1][0] = tag;
	el->el_display[1][1] = MB_FILL_CHAR;
	capability(el, L"am", L"yes");
	capability(el, L"xn", L"yes");
	el->el_cursor.h = 3;
	start = checkpoint(out);
	terminal_overwrite(el, &bang, 1);
	expect_output(out, start, "!\033[31m\xe4\xb8\xad");
	CHECK(el->el_cursor.h == 2 && el->el_cursor.v == 1);
	plain_capabilities(el);
}

static void
refresh_paths(EditLine *el, FILE *out)
{
	wint_t expected[] = {
		EL_LITERAL, MB_FILL_CHAR, EL_LITERAL | (wint_t)1, ' ',
		'A', L'\u03bb', L'\u4e2d', MB_FILL_CHAR, 'Z'
	};
	char bytes[1024];
	size_t i, n, spaces;
	long start;

	screen(el, 3, 24);
	CHECK(el_wset(el, EL_PROMPT_ESC, color_prompt, L'\001') == 0);
	input_line(el, L"A\u03bb\u4e2dZ");
	start = checkpoint(out);
	re_refresh(el);
	expect_output(out, start,
	    "\033[31m\xe4\xb8\xad\033[0m> A\xce\xbb\xe4\xb8\xadZ");
	for (i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		CHECK(el->el_display[0][i] == expected[i]);
	for (; i < 24; i++)
		CHECK(el->el_display[0][i] == ' ');
	CHECK(el->el_display[0][24] == 0);
	CHECK(el->el_cursor.h == 9);
	start = checkpoint(out);
	re_refresh(el);
	/* A no-change refresh may move by reprinting cells, but must retain tags. */
	expect_output(out, start,
	    "\r\033[31m\xe4\xb8\xad\033[0m> A\xce\xbb\xe4\xb8\xadZ");
	for (i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		CHECK(el->el_display[0][i] == expected[i]);
	input_line(el, L"AB\u03bb\u4e2dZ");
	re_refresh(el);
	CHECK(el->el_display[0][5] == 'B');
	CHECK(el->el_display[0][6] == L'\u03bb');
	CHECK(el->el_display[0][7] == L'\u4e2d');
	CHECK(el->el_display[0][8] == MB_FILL_CHAR);
	input_line(el, L"A\u03bb\u4e2dZ");
	re_refresh(el);
	for (i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		CHECK(el->el_display[0][i] == expected[i]);

	/* A long shared suffix makes the diff use re_insert and re_delete. */
	input_line(el, L"A\u03bb\u4e2dZabcdef");
	re_refresh(el);
	capability(el, L"ic", L"\033[@");
	capability(el, L"dc", L"\033[P");
	input_line(el, L"AB\u03bb\u4e2dZabcdef");
	start = checkpoint(out);
	re_refresh(el);
	(void)read_output(out, start, bytes, sizeof(bytes));
	CHECK(strstr(bytes, "\033[@") != NULL);
	CHECK(el->el_display[0][5] == 'B');
	CHECK(el->el_display[0][6] == L'\u03bb');
	CHECK(el->el_display[0][7] == L'\u4e2d');
	CHECK(el->el_display[0][8] == MB_FILL_CHAR);
	CHECK(el->el_display[0][15] == 'f');
	input_line(el, L"A\u03bb\u4e2dZabcdef");
	start = checkpoint(out);
	re_refresh(el);
	(void)read_output(out, start, bytes, sizeof(bytes));
	CHECK(strstr(bytes, "\033[P") != NULL);
	for (i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		CHECK(el->el_display[0][i] == expected[i]);
	CHECK(el->el_display[0][14] == 'f');
	CHECK(el->el_display[0][15] == ' ');
	plain_capabilities(el);

	CHECK(el_wset(el, EL_PROMPT, empty_prompt) == 0);
	screen(el, 3, 8);
	input_line(el, L"12345678\u4e2dABC");
	re_refresh(el);
	CHECK(el->el_refresh.r_oldcv == 1);
	CHECK(el->el_display[1][0] == L'\u4e2d');
	CHECK(el->el_display[1][1] == MB_FILL_CHAR);
	input_line(el, L"");
	start = checkpoint(out);
	re_refresh(el);
	n = read_output(out, start, bytes, sizeof(bytes));
	for (i = spaces = 0; i < n; i++)
		if (bytes[i] == ' ')
			spaces++;
	CHECK(spaces == 16); /* Two full cell rows, not wchar_t half-rows. */
	CHECK(el->el_display[1][0] == 0);
	CHECK(el->el_refresh.r_oldcv == 0);
}

int
main(int argc, char **argv)
{
	EditLine *el;
	FILE *out;
	int fd;

	CHECK(argc == 2);
	CHECK(setlocale(LC_ALL, "C.UTF-8") != NULL);
	CHECK(MB_CUR_MAX > 1);
	CHECK(wcwidth(L'\u4e2d') == 2 && wcwidth(L'\u03bb') == 1);
	fd = open(argv[1], O_CREAT | O_EXCL | O_RDWR, 0600);
	CHECK(fd >= 0);
	out = fdopen(fd, "w+b");
	CHECK(out != NULL);
	el = el_init("display-cells", out, out, stderr);
	CHECK(el != NULL);
	CHECK(el_wset(el, EL_EDITOR, L"emacs") == 0);
	CHECK(el_wset(el, EL_PROMPT, empty_prompt) == 0);
	CHECK(el_wset(el, EL_RPROMPT, empty_prompt) == 0);
	plain_capabilities(el);
	output_paths(el, out);
	wrapping_and_scrolling(el, out);
	refresh_paths(el, out);
	el_end(el);
	CHECK(fclose(out) == 0);
	puts("display-cells: native mixed-width regressions passed");
	return EXIT_SUCCESS;
}

#define WIN32_LEAN_AND_MEAN

typedef unsigned long dword;
typedef unsigned short wchar_t;

typedef struct {
  dword cb;
  wchar_t *reserved;
  wchar_t *desktop;
  wchar_t *title;
  dword x;
  dword y;
  dword x_size;
  dword y_size;
  dword x_chars;
  dword y_chars;
  dword fill_attribute;
  dword flags;
  unsigned short show_window;
  unsigned short reserved_size;
  unsigned char *reserved_data;
  void *standard_input;
  void *standard_output;
  void *standard_error;
} startup_info;

typedef struct {
  void *process;
  void *thread;
  dword process_id;
  dword thread_id;
} process_information;

__declspec(dllimport) dword __stdcall GetModuleFileNameW(
    void *module, wchar_t *filename, dword size);
__declspec(dllimport) wchar_t *__stdcall GetCommandLineW(void);
__declspec(dllimport) int __stdcall SetEnvironmentVariableW(
    const wchar_t *name, const wchar_t *value);
__declspec(dllimport) void *__stdcall LocalFree(void *memory);
__declspec(dllimport) void *__stdcall GetStdHandle(dword handle);
__declspec(dllimport) int __stdcall WriteFile(
    void *file, const void *buffer, dword bytes_to_write,
    dword *bytes_written, void *overlapped);
__declspec(dllimport) wchar_t **__stdcall CommandLineToArgvW(
    const wchar_t *command_line, int *argument_count);
__declspec(dllimport) int __stdcall CreateProcessW(
    const wchar_t *application_name, wchar_t *command_line,
    void *process_attributes, void *thread_attributes, int inherit_handles,
    dword creation_flags, void *environment, const wchar_t *current_directory,
    startup_info *startup, process_information *process);
__declspec(dllimport) dword __stdcall WaitForSingleObject(
    void *handle, dword milliseconds);
__declspec(dllimport) int __stdcall GetExitCodeProcess(
    void *process, dword *exit_code);
__declspec(dllimport) int __stdcall CloseHandle(void *handle);

#define PATH_CAPACITY 32768
#define STDIN_HANDLE ((dword)-10)
#define STDOUT_HANDLE ((dword)-11)
#define STDERR_HANDLE ((dword)-12)
#define USE_STANDARD_HANDLES 0x00000100
#define WAIT_FOREVER ((dword)-1)
#define WAIT_SUCCEEDED 0

static unsigned int string_length(const wchar_t *value) {
  unsigned int length = 0;
  while (value[length] != L'\0')
    ++length;
  return length;
}

static int strings_equal(const wchar_t *left, const wchar_t *right) {
  while (*left != L'\0' && *left == *right) {
    ++left;
    ++right;
  }
  return *left == *right;
}

static wchar_t *find_substring(wchar_t *value, const wchar_t *needle) {
  for (; *value != L'\0'; ++value) {
    const wchar_t *left = value;
    const wchar_t *right = needle;
    while (*right != L'\0' && *left == *right) {
      ++left;
      ++right;
    }
    if (*right == L'\0')
      return value;
  }
  return (wchar_t *)0;
}

static wchar_t *last_separator(wchar_t *value) {
  wchar_t *result = (wchar_t *)0;
  for (; *value != L'\0'; ++value) {
    if (*value == L'\\' || *value == L'/')
      result = value;
  }
  return result;
}

static int append(wchar_t *target, unsigned int capacity,
                  const wchar_t *suffix) {
  unsigned int used = string_length(target);
  unsigned int added = string_length(suffix);
  unsigned int index;

  if (used + added >= capacity)
    return 0;
  for (index = 0; index <= added; ++index)
    target[used + index] = suffix[index];
  return 1;
}

static int append_repeated(wchar_t *target, unsigned int capacity,
                           unsigned int *used, wchar_t value,
                           unsigned int count) {
  unsigned int index;

  if (*used + count >= capacity)
    return 0;
  for (index = 0; index < count; ++index)
    target[(*used)++] = value;
  target[*used] = L'\0';
  return 1;
}

static int append_quoted_argument(wchar_t *target, unsigned int capacity,
                                  const wchar_t *argument) {
  unsigned int used = string_length(target);
  unsigned int backslashes = 0;

  if (!append_repeated(target, capacity, &used, L'"', 1))
    return 0;

  while (*argument != L'\0') {
    if (*argument == L'\\') {
      ++backslashes;
    } else if (*argument == L'"') {
      if (!append_repeated(
              target, capacity, &used, L'\\', backslashes * 2 + 1) ||
          !append_repeated(target, capacity, &used, L'"', 1))
        return 0;
      backslashes = 0;
    } else {
      if (!append_repeated(
              target, capacity, &used, L'\\', backslashes) ||
          !append_repeated(target, capacity, &used, *argument, 1))
        return 0;
      backslashes = 0;
    }
    ++argument;
  }

  return append_repeated(target, capacity, &used, L'\\', backslashes * 2) &&
         append_repeated(target, capacity, &used, L'"', 1);
}

static int report_error(const char *message) {
  dword length = 0;
  dword written;

  while (message[length] != '\0')
    ++length;
  WriteFile(GetStdHandle(STDERR_HANDLE), message, length, &written, (void *)0);
  return 1;
}

int main(void) {
  static const wchar_t marker[] =
      L"\\usr\\local\\libexec\\msys2-woarm64\\";
  wchar_t executable[PATH_CAPACITY];
  wchar_t directory[PATH_CAPACITY];
  wchar_t bash[PATH_CAPACITY];
  wchar_t script[PATH_CAPACITY];
  wchar_t command_line[PATH_CAPACITY];
  wchar_t *root_end;
  wchar_t *filename;
  const wchar_t *compiler_name;
  startup_info startup = {0};
  process_information process = {0};
  unsigned int length;
  wchar_t **argv;
  int argc;
  int index;
  dword exit_code;

  argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  if (argv == (wchar_t **)0)
    return report_error("Unable to parse native compiler arguments.\n");

  length = GetModuleFileNameW((void *)0, executable, PATH_CAPACITY);
  if (length == 0 || length >= PATH_CAPACITY)
    return report_error("Unable to locate the native compiler launcher.\n");

  directory[0] = L'\0';
  if (!append(directory, PATH_CAPACITY, executable))
    return report_error("Native compiler launcher path is too long.\n");

  filename = last_separator(directory);
  if (filename == (wchar_t *)0)
    return report_error("Native compiler launcher path has no directory.\n");
  ++filename;

  if (strings_equal(filename, L"woarm64-gcc.exe"))
    compiler_name = L"woarm64-gcc";
  else if (strings_equal(filename, L"woarm64-g++.exe"))
    compiler_name = L"woarm64-g++";
  else
    return report_error("Unsupported native compiler launcher name.\n");

  root_end = find_substring(executable, marker);
  if (root_end == (wchar_t *)0)
    return report_error("Native compiler launcher is outside its MSYS root.\n");
  *root_end = L'\0';

  bash[0] = L'\0';
  if (!append(bash, PATH_CAPACITY, executable) ||
      !append(bash, PATH_CAPACITY, L"\\usr\\bin\\bash.exe"))
    return report_error("MSYS Bash path is too long.\n");

  *filename = L'\0';
  script[0] = L'\0';
  if (!append(script, PATH_CAPACITY, directory) ||
      !append(script, PATH_CAPACITY, compiler_name))
    return report_error("Compiler normalizer path is too long.\n");

  if (!SetEnvironmentVariableW(
          L"WOARM64_NATIVE_COMPILER_NAME", compiler_name))
    return report_error("Unable to select the native compiler.\n");

  command_line[0] = L'\0';
  if (!append_quoted_argument(command_line, PATH_CAPACITY, bash) ||
      !append(command_line, PATH_CAPACITY, L" ") ||
      !append_quoted_argument(command_line, PATH_CAPACITY, script))
    return report_error("Native compiler command line is too long.\n");
  for (index = 1; index < argc; ++index) {
    if (!append(command_line, PATH_CAPACITY, L" ") ||
        !append_quoted_argument(command_line, PATH_CAPACITY, argv[index]))
      return report_error("Native compiler command line is too long.\n");
  }

  startup.cb = sizeof(startup);
  startup.flags = USE_STANDARD_HANDLES;
  startup.standard_input = GetStdHandle(STDIN_HANDLE);
  startup.standard_output = GetStdHandle(STDOUT_HANDLE);
  startup.standard_error = GetStdHandle(STDERR_HANDLE);
  if (!CreateProcessW(
          bash, command_line, (void *)0, (void *)0, 1, 0, (void *)0,
          (const wchar_t *)0, &startup, &process)) {
    LocalFree(argv);
    return report_error("Unable to start MSYS Bash for native compilation.\n");
  }
  LocalFree(argv);
  CloseHandle(process.thread);
  if (WaitForSingleObject(process.process, WAIT_FOREVER) != WAIT_SUCCEEDED ||
      !GetExitCodeProcess(process.process, &exit_code)) {
    CloseHandle(process.process);
    return report_error("Unable to read the native compiler exit code.\n");
  }
  CloseHandle(process.process);
  return (int)exit_code;
}

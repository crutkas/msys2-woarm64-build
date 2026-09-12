/* Emit a generation-bound contract before an MSYS process exits or execs. */

#include <ctype.h>
#include <errno.h>
#include <process.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/cygwin.h>
#include <sys/wait.h>
#include <unistd.h>
#include <windows.h>
#include <tlhelp32.h>

static int
process_identity (DWORD pid, ULARGE_INTEGER *created)
{
  FILETIME creation, exit_time, kernel_time, user_time;
  HANDLE process = OpenProcess (PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);

  if (!process)
    return -1;
  if (!GetProcessTimes (process, &creation, &exit_time, &kernel_time, &user_time))
    {
      CloseHandle (process);
      return -1;
    }
  CloseHandle (process);
  created->LowPart = creation.dwLowDateTime;
  created->HighPart = creation.dwHighDateTime;
  return 0;
}

static DWORD
parent_pid (DWORD pid)
{
  PROCESSENTRY32W entry = { 0 };
  HANDLE snapshot = CreateToolhelp32Snapshot (TH32CS_SNAPPROCESS, 0);

  entry.dwSize = sizeof entry;
  if (snapshot == INVALID_HANDLE_VALUE
      || !Process32FirstW (snapshot, &entry))
    {
      if (snapshot != INVALID_HANDLE_VALUE)
	CloseHandle (snapshot);
      return 0;
    }
  do
    {
      if (entry.th32ProcessID == pid)
	{
	  CloseHandle (snapshot);
	  return entry.th32ParentProcessID;
	}
    }
  while (Process32NextW (snapshot, &entry));
  CloseHandle (snapshot);
  return 0;
}

static int
valid_contract_name (const char *name)
{
  const unsigned char *p = (const unsigned char *) name;

  if (!*p)
    return 0;
  for (; *p; ++p)
    if (!isalnum (*p) && *p != '-' && *p != '_' && *p != '.')
      return 0;
  return 1;
}

static int
valid_sha256 (const char *value)
{
  size_t i;

  if (strlen (value) != 64)
    return 0;
  for (i = 0; i < 64; ++i)
    if (!isxdigit ((unsigned char) value[i]))
      return 0;
  return 1;
}

static int
write_contract (const char *name, int status, DWORD pid,
		ULARGE_INTEGER created, DWORD ppid,
		ULARGE_INTEGER parent_created)
{
  const char *root = getenv ("WOARM64_NATIVE_EXIT_DIR");
  const char *source = getenv ("WOARM64_EXIT_CONTRACT_SOURCE_SHA256");
  char path[4096];
  FILE *stream;
  int length;
  int failed;

  if (!root || !source || !valid_contract_name (name)
      || !valid_sha256 (source) || !ppid)
    return -1;
  length = snprintf (path, sizeof path,
		     "%s/msys-exit-contract-%lu-%llu.json", root,
		     (unsigned long) pid,
		     (unsigned long long) created.QuadPart);
  if (length <= 0 || (size_t) length >= sizeof path)
    return -1;

  stream = fopen (path, "wb");
  if (!stream)
    return -1;
  failed = fprintf (stream,
		    "{\"expected_exit_contract\":\"%s\","
		    "\"probe_source_sha256\":\"%s\","
		    "\"child_pid\":%lu,\"child_created\":%llu,"
		    "\"parent_pid\":%lu,\"parent_created\":%llu,"
		    "\"expected_raw_exit\":%u,\"portable_exit\":%d}\n",
		    name, source, (unsigned long) pid,
		    (unsigned long long) created.QuadPart,
		    (unsigned long) ppid,
		    (unsigned long long) parent_created.QuadPart,
		    (unsigned int) status << 8, status) < 0;
  if (fclose (stream))
    failed = 1;
  if (failed)
    return -1;
  return 0;
}

static int
write_current_contract (const char *name, int status)
{
  ULARGE_INTEGER created, parent_created;
  DWORD pid = GetCurrentProcessId ();
  DWORD ppid = parent_pid (pid);

  if (!ppid || process_identity (pid, &created)
      || process_identity (ppid, &parent_created))
    return -1;
  return write_contract (name, status, pid, created, ppid, parent_created);
}

static int
spawn_contract (const char *name, int expected, char **argv)
{
  ULARGE_INTEGER created, parent_created;
  pid_t child;
  int status;
  DWORD pid = GetCurrentProcessId ();
  DWORD winpid;

  child = spawnv (_P_NOWAIT, argv[0], (const char *const *) argv);
  if (child < 0)
    return -1;
  winpid = (DWORD) cygwin_internal (CW_CYGWIN_PID_TO_WINPID, child);
  if (!winpid || process_identity (winpid, &created)
      || process_identity (pid, &parent_created)
      || write_contract (name, expected, winpid, created, pid, parent_created))
    {
      waitpid (child, NULL, 0);
      return -1;
    }
  if (waitpid (child, &status, 0) != child
      || !WIFEXITED (status) || WEXITSTATUS (status) != expected)
    {
      errno = ECHILD;
      return -1;
    }
  return 0;
}

int
main (int argc, char **argv)
{
  char *end;
  long status;

  if (argc < 4
      || (strcmp (argv[1], "--exit") && strcmp (argv[1], "--spawn")))
    {
      fprintf (stderr,
	       "usage: msys-exit-contract --exit NAME STATUS\n"
	       "       msys-exit-contract --spawn NAME STATUS PROGRAM [ARG...]\n");
      return 2;
    }

  errno = 0;
  status = strtol (argv[3], &end, 10);
  if (errno || *end || status < 0 || status > 255)
    return 2;
  if (!strcmp (argv[1], "--exit"))
    {
      if (argc != 4)
	return 2;
      if (write_current_contract (argv[2], status))
	{
	  perror ("write exit contract");
	  return 125;
	}
      _exit ((int) status);
    }

  if (argc < 5)
    return 2;
  if (spawn_contract (argv[2], status, &argv[4]))
    {
      perror ("spawn exit contract");
      return 125;
    }
  return 0;
}

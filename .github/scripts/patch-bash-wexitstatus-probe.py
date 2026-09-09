"""Instrument Bash's exact wait-status configure probe with a generation-bound exit contract."""

import argparse
import hashlib
import json
from pathlib import Path
import re


PROBE_SOURCE_SHA256 = "57f1200815161b4643d1db5b719a395fe97000271119b74696af7a151fffe03f"
CONTRACT = "bash-wexitstatus-offset-v1"
MACRO_PATTERN = re.compile(
    r"AC_DEFUN\(BASH_STRUCT_WEXITSTATUS_OFFSET,\n\[(.*?)\]\)\n\nAC_DEFUN\(\[BASH_FUNC_SBRK\]",
    re.S,
)
INCLUDES = """#include <stdlib.h>
#include <unistd.h>

#include <sys/wait.h>"""
INSTRUMENTED_INCLUDES = """#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <windows.h>
#include <tlhelp32.h>

#include <sys/wait.h>"""
CHILD = """  if (pid == 0)
    exit (42);"""
INSTRUMENTED_CHILD = f"""  if (pid == 0)
    {{
      const char *relay_root = getenv ("WOARM64_NATIVE_EXIT_DIR");
      FILETIME created, ended, kernel_time, user_time;
      FILETIME parent_created, parent_ended, parent_kernel, parent_user;
      ULARGE_INTEGER created_value, parent_created_value;
      char relay_path[4096];
      FILE *relay;
      HANDLE snapshot, parent;
      PROCESSENTRY32W entry;
      DWORD child_pid = GetCurrentProcessId ();
      DWORD parent_pid = 0;
      int length;

      if (relay_root == 0
          || !GetProcessTimes (GetCurrentProcess (), &created, &ended, &kernel_time, &user_time))
        _exit (253);
      snapshot = CreateToolhelp32Snapshot (TH32CS_SNAPPROCESS, 0);
      entry.dwSize = sizeof (entry);
      if (snapshot == INVALID_HANDLE_VALUE || !Process32FirstW (snapshot, &entry))
        _exit (249);
      do
        {{
          if (entry.th32ProcessID == child_pid)
            {{
              parent_pid = entry.th32ParentProcessID;
              break;
            }}
        }}
      while (Process32NextW (snapshot, &entry));
      CloseHandle (snapshot);
      parent = OpenProcess (PROCESS_QUERY_LIMITED_INFORMATION, FALSE, parent_pid);
      if (parent_pid == 0 || parent == 0
          || !GetProcessTimes (parent, &parent_created, &parent_ended,
                               &parent_kernel, &parent_user))
        _exit (248);
      CloseHandle (parent);
      created_value.LowPart = created.dwLowDateTime;
      created_value.HighPart = created.dwHighDateTime;
      parent_created_value.LowPart = parent_created.dwLowDateTime;
      parent_created_value.HighPart = parent_created.dwHighDateTime;
      length = snprintf (relay_path, sizeof (relay_path),
                         "%s/bash-wexitstatus-offset-%lu-%llu.json", relay_root,
                         (unsigned long) child_pid,
                         (unsigned long long) created_value.QuadPart);
      if (length <= 0 || (size_t) length >= sizeof (relay_path))
        _exit (252);
      relay = fopen (relay_path, "wb");
      if (relay == 0)
        _exit (251);
      if (fprintf (relay,
                   "{{\\\"expected_exit_contract\\\":\\\"bash-wexitstatus-offset-v1\\\","
                   "\\\"probe_source_sha256\\\":\\\"{PROBE_SOURCE_SHA256}\\\","
                   "\\\"child_pid\\\":%lu,\\\"child_created\\\":%llu,"
                   "\\\"parent_pid\\\":%lu,\\\"parent_created\\\":%llu,"
                   "\\\"expected_raw_exit\\\":10752,\\\"portable_exit\\\":42}}\\n",
                   (unsigned long) child_pid,
                   (unsigned long long) created_value.QuadPart,
                   (unsigned long) parent_pid,
                   (unsigned long long) parent_created_value.QuadPart) < 0
          || fclose (relay) != 0)
        _exit (250);
      exit (42);
    }}"""

PROBE_PROGRAM = f"""{INSTRUMENTED_INCLUDES}

int
main (void)
{{
  pid_t pid, waited;
  int status, i, value;

  status = 0;
  pid = fork ();
  {INSTRUMENTED_CHILD}
  waited = wait (&status);
  if (waited != pid)
    exit (255);
  for (i = 0; i < (sizeof (status) * 8); i++)
    {{
      value = (status >> i) & 0xff;
      if (value == 42)
        exit (i);
    }}
  exit (254);
}}
"""


def patch(path):
    text = path.read_text(encoding="utf-8")
    if text.count(INCLUDES) != 1 or text.count(CHILD) != 1:
        raise ValueError(f"Expected one uninstrumented Bash wait-status probe in {path}")
    path.write_text(
        text.replace(INCLUDES, INSTRUMENTED_INCLUDES).replace(CHILD, INSTRUMENTED_CHILD),
        encoding="utf-8",
        newline="\n",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    aclocal = args.source / "aclocal.m4"
    configure = args.source / "configure"
    macro = MACRO_PATTERN.search(aclocal.read_text(encoding="utf-8"))
    if macro is None or hashlib.sha256(macro.group(1).encode()).hexdigest() != PROBE_SOURCE_SHA256:
        raise ValueError("Bash wait-status macro differs from the sealed expected source")
    before = {
        str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (aclocal, configure)
    }
    patch(aclocal)
    patch(configure)
    probe_program = args.source.parent / "bash-wexitstatus-probe.c"
    probe_program.write_text(PROBE_PROGRAM, encoding="utf-8", newline="\n")
    after = {
        str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (aclocal, configure)
    }
    receipt = {
        "schema": 1,
        "contract": CONTRACT,
        "probe_source_sha256": PROBE_SOURCE_SHA256,
        "files": [
            {"path": path.name, "before_sha256": before[path.name], "after_sha256": after[path.name]}
            for path in (aclocal, configure)
        ],
        "standalone_probe": {
            "path": probe_program.name,
            "sha256": hashlib.sha256(probe_program.read_bytes()).hexdigest(),
        },
    }
    receipt_path = args.source.parent / "bash-wexitstatus-probe.instrumentation.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

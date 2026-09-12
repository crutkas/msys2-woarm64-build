import json
import os

names = ("WOARM64_ENV_INHERITED", "WOARM64_ENV_NEW", "CCACHE_DISABLE", "TMPDIR", "PATH", "MSYSTEM")
print(json.dumps({"child": "native-Windows-Python",
                  "environment": {name: os.environ.get(name) for name in names},
                  "system_variables_present": {name: name in os.environ for name in ("SYSTEMROOT", "WINDIR")}},
                 sort_keys=True))

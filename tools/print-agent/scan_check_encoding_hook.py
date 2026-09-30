"""Keep Russian setup/help usable in redirected Windows packaged output."""

import sys

for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

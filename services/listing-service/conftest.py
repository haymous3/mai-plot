"""Service-root conftest — prepends this service's directory to sys.path
so `import app` resolves to *this* service's app/ regardless of which
other workspace member's editable install happens to be on sys.path first.

Required because every service exposes a top-level package called `app`
and Python caches the first one it imports across the venv. Per-service
pytest invocation (the CI loop pattern) plus this conftest gives each
service a clean, isolated import root.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).resolve().parent)

# uv installs every workspace member as editable via a .pth file that
# adds the service dir to sys.path in alphabetical order. Whichever
# sibling service is alphabetically first wins `import app`. We can't
# just guard with `if _SERVICE_ROOT not in sys.path` because this
# service IS in sys.path (just behind the alphabetically-earlier ones).
# Remove any existing entry first, then prepend so this service wins.
while _SERVICE_ROOT in sys.path:
    sys.path.remove(_SERVICE_ROOT)
sys.path.insert(0, _SERVICE_ROOT)

# Flush any pre-cached `app*` entry so the next import re-resolves
# through the updated sys.path and lands on this service.
for _mod in list(sys.modules):
    if _mod == "app" or _mod.startswith("app."):
        del sys.modules[_mod]

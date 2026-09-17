#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Stand-in Foot process for terminal-operation supervision tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def main() -> int:
    if len(sys.argv) < 3 or not sys.argv[1].startswith("--title="):
        return 64

    if os.environ.get("VANHYPRARCH_TEST_FOOT_SKIP_CHILD") == "1":
        return int(os.environ.get("VANHYPRARCH_TEST_FOOT_STATUS", "0"))

    delay = float(os.environ.get("VANHYPRARCH_TEST_FOOT_DELAY", "0"))
    if delay > 0:
        time.sleep(delay)

    child = subprocess.run(
        sys.argv[2:],
        input=b"\n",
        check=False,
    )
    forced_status = os.environ.get("VANHYPRARCH_TEST_FOOT_STATUS")
    return int(forced_status) if forced_status is not None else child.returncode


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Deterministic process-lifecycle fixture for SystemComponentsActions."""

from __future__ import annotations

import os
import sys
import time


DELAY_SECONDS = 0.05


def main() -> int:
    time.sleep(DELAY_SECONDS)

    executable = os.path.basename(sys.argv[0])
    if len(sys.argv) == 2 and sys.argv[1] == "reload":
        return 1 if executable.endswith("-failure") else 0

    if executable.startswith("component-manager-"):
        return 1 if executable.endswith("-failure") else 0

    return 64


if __name__ == "__main__":
    raise SystemExit(main())

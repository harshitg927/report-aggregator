# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Module entry point so ``python -m report_aggregator ...`` works.

Preferred invocation form when the package is installed to a non-PATH location
(e.g. FOSSology's ``pip install --target=$HOME/pythondeps`` layout, where the
``report-aggregator`` console script may not be on PATH).
"""

from __future__ import annotations

import sys

from report_aggregator.cli import main

if __name__ == "__main__":
    sys.exit(main())

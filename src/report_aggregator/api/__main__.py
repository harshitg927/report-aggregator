# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Run the report-aggregator API with uvicorn.

Usage:
    python -m report_aggregator.api
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("REPORT_AGGREGATOR_API_HOST", "127.0.0.1")
    port = int(os.environ.get("REPORT_AGGREGATOR_API_PORT", "8000"))
    uvicorn.run("report_aggregator.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

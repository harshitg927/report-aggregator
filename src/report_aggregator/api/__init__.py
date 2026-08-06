# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""FastAPI service exposing the report-aggregator engine over HTTP.

This service reuses the merge/edit engine in-process (no CLI shell-out).

SECURITY NOTE: This is a local development service. It has NO authentication
or access control and permissive CORS for localhost. Do not expose it to a
public network without adding auth and tightening CORS.
"""

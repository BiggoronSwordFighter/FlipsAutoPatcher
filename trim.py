#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trim.py - N64 ROM "garbage data" trimmer (64 MiB)

This module intentionally contains **no GUI code**.

Purpose
-------
Some flash carts complain that certain N64 ROMs are "too large" even though the
extra data past 64 MiB is effectively unused "garbage". This optional helper
truncates (hard-trims) the ROM file to exactly 64 MiB by omitting all bytes
after 64 MiB.

WARNING: This can produce a broken ROM. If the data past 64 MiB contains
anything important for a specific hack/build, truncating it may introduce bugs,
crashes, or missing content.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

N64_EXTENSIONS = {".z64", ".n64", ".v64"}
SIZE_LIMIT_BYTES = 64 * 1024 * 1024  # 64 MiB


def _log(log_fn: Optional[Callable[[str], None]], msg: str) -> None:
    """_log helper.

    Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
    """
    if callable(log_fn):
        try:
            log_fn(msg)
        except Exception:
            pass


def trim_to_64mb(*, rom_path: str, enabled: bool, log_fn: Optional[Callable[[str], None]] = None) -> str:
    """Trim an N64 ROM file to 64 MiB (in-place) if enabled.

    Parameters
    ----------
    rom_path:
        Path to the ROM file on disk.
    enabled:
        If False, this function is a no-op.
    log_fn:
        Optional logger callback (e.g., GUI's log_message). If provided, messages
        are sent there; otherwise the function stays silent.

    Returns
    -------
    str
        The final ROM path (same as input; file may be truncated).
    """
    if not enabled:
        return rom_path

    try:
        ext = os.path.splitext(rom_path)[1].lower()
    except Exception:
        return rom_path

    # Only intended for N64 ROM containers.
    if ext not in N64_EXTENSIONS:
        return rom_path

    try:
        current_size = os.path.getsize(rom_path)
    except Exception as e:
        _log(log_fn, f"Trim error: could not read file size: {e}")
        return rom_path

    if current_size <= SIZE_LIMIT_BYTES:
        _log(log_fn, f"Trim skipped: ROM is already {current_size} bytes (<= 64MiB).")
        return rom_path

    # Truncate the existing file directly. This is much more reliable on Windows
    # than rewriting to a temp file and replacing the original right after Flips
    # has created it.
    try:
        with open(rom_path, "r+b") as f:
            f.truncate(SIZE_LIMIT_BYTES)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass

        try:
            final_size = os.path.getsize(rom_path)
        except Exception:
            final_size = None

        if final_size == SIZE_LIMIT_BYTES:
            _log(log_fn, "Trimmed ROM to 64MiB (garbage data removed past 64MiB).")
        elif final_size is not None:
            _log(log_fn, f"Trim warning: expected {SIZE_LIMIT_BYTES} bytes, got {final_size} bytes.")
        else:
            _log(log_fn, "Trim complete.")
    except Exception as e:
        _log(log_fn, f"Trim error: {e}")

    return rom_path

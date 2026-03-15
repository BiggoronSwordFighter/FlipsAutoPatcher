#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================= Flips Auto Patcher (Bulk Patching) =============================

This module implements the "Bulk Patching" feature as a separate file from main.py.

When enabled in the GUI, the app will:
  - Ensure ./bulk patching/ and ./bulk patching/base roms/ exist (next to the app)
  - Automatically apply every .bps/.ips found in ./bulk patching/ against ROMs in ./bulk patching/base roms/
  - For .bps: choose base ROM by Source CRC32 in patch metadata
  - For .ips: try each base ROM until a patch applies successfully

This file intentionally stays minimal and uses the existing app instance for:
  - logging
  - suffix options
  - force/ignore-checksum option
  - optional post-processing steps (byteswap / trim)
"""

from __future__ import annotations

import os
import subprocess
from typing import Dict, List, Tuple

import endian_swap as rom_byteswap
from utils import (
    calculate_crc32,
    calculate_md5,
    calculate_sha1,
    calculate_zle_hash,
    get_patch_metadata,
    get_ips_requirements,
    get_ips_metadata,
)


from typing import Callable, Optional


# ----------------------------
# Bulk post-processing helpers
# ----------------------------

def _bulk_get_byteswap_mode(app) -> str:
    """Read the GUI's N64 endian selection.

    main.py uses `byteswap_mode` (StringVar) with values:
      - 'disable'
      - 'z64' / 'n64' / 'v64'
    Some older variants used `byte_swap_enabled` + `byte_swap_endian`.
    """
    try:
        mode = app.byteswap_mode.get()
        return str(mode) if mode else "disable"
    except Exception:
        pass

    # Fallback: legacy vars
    try:
        enabled = bool(app.byte_swap_enabled.get())
        if not enabled:
            return "disable"
        endian = app.byte_swap_endian.get()
        endian = str(endian).lower().strip()
        if endian in ("z64", "n64", "v64"):
            return endian
    except Exception:
        pass

    return "disable"


def _bulk_apply_byteswap_to_output(app, patched_rom_path: str, log: Callable[[str], None]) -> str:
    """Convert patched N64 ROM to selected endian and rename extension accordingly.

    This replicates the intended behavior of main.py's _apply_byteswap_to_output
    even if that method is incomplete in the user's local main.py.
    """
    mode = _bulk_get_byteswap_mode(app)
    if mode == "disable":
        return patched_rom_path

    ext = os.path.splitext(patched_rom_path)[1].lower()
    if ext not in {".z64", ".n64", ".v64"}:
        # Match main.py message behavior.
        try:
            log("File does not use endian swapping.")
        except Exception:
            pass
        return patched_rom_path

    try:
        with open(patched_rom_path, "rb") as f:
            data = f.read()
    except Exception as e:
        log(f"Byte-swap read error: {e}")
        return patched_rom_path

    try:
        src_fmt = rom_byteswap.detect_format(data)
    except Exception:
        # Invalid magic; don't touch.
        try:
            log("File does not use endian swapping.")
        except Exception:
            pass
        return patched_rom_path

    dst_fmt = mode  # 'z64' / 'n64' / 'v64'
    if dst_fmt not in ("z64", "n64", "v64"):
        return patched_rom_path

    try:
        out_data = rom_byteswap.convert(data, src_fmt, dst_fmt)
    except Exception as e:
        log(f"Byte-swap convert error: {e}")
        return patched_rom_path

    base_no_ext = os.path.splitext(patched_rom_path)[0]
    out_path = f"{base_no_ext}.{dst_fmt}"

    try:
        with open(out_path, "wb") as f:
            f.write(out_data)

        # Remove old file if the extension changed.
        if os.path.abspath(out_path) != os.path.abspath(patched_rom_path):
            try:
                os.remove(patched_rom_path)
            except Exception:
                pass

        log(f"Byte-swap complete → {os.path.basename(out_path)}")
        return out_path
    except Exception as e:
        log(f"Byte-swap write error: {e}")
        return patched_rom_path


def _bulk_apply_trim_to_64mb_output(app, patched_rom_path: str, log: Callable[[str], None]) -> str:
    """Optionally trim the patched output ROM to 64MiB (N64 only)."""
    try:
        enabled = bool(app.trim_64mb.get())
    except Exception:
        # Fallback: legacy var name
        try:
            enabled = bool(app.trim_enabled.get())
        except Exception:
            enabled = False

    if not enabled:
        return patched_rom_path

    ext = os.path.splitext(patched_rom_path)[1].lower()
    if ext not in {".z64", ".n64", ".v64"}:
        return patched_rom_path

    try:
        import trim as data_trim
        data_trim.trim_to_64mb(
            rom_path=patched_rom_path,
            enabled=True,
            log_fn=log,
        )
    except Exception as e:
        log(f"Trim error: {e}")
    return patched_rom_path


def _bulk_postprocess(app, patched_rom_path: str, log: Callable[[str], None]) -> str:
    patched_rom_path = _bulk_apply_byteswap_to_output(app, patched_rom_path, log)
    patched_rom_path = _bulk_apply_trim_to_64mb_output(app, patched_rom_path, log)
    return patched_rom_path


def _bulk_launch_emulator_if_configured(app, patched_rom_path: str, log: Callable[[str], None]) -> None:
    try:
        launcher = getattr(app, "launch_emulator_if_configured", None)
        if callable(launcher):
            launcher(patched_rom_path)
    except Exception as e:
        try:
            log(f"Emulator launch error: {e}")
        except Exception:
            pass


def _log_utils_hashes(log, file_path: str, label: str) -> None:
    """Log hash info using utils.py helpers (CRC32 / MD5 / SHA-1 / ZLE).

    Bulk mode should rely on utils.py for hash logic, and should also display
    the same verification info users see in the normal (non-bulk) workflow.
    """
    try:
        crc32 = calculate_crc32(file_path)
        md5 = calculate_md5(file_path)
        sha1 = calculate_sha1(file_path)
        zle = calculate_zle_hash(file_path)
        log(f"{label} Hashes ({os.path.basename(file_path)}):")
        log(f"  CRC32: {crc32:#010x}")
        log(f"  MD5:   {md5}")
        log(f"  SHA-1: {sha1}")
        log(f"  ZLE:   {zle}")
    except Exception as e:
        log(f"{label} hash display error for {os.path.basename(file_path)}: {e}")



def _ips_requirements(patch_file_path: str):
    """Return (min_required_size, trunc_size) for an IPS patch.

    IPS patches don't embed a source CRC like BPS. To reduce false 'successful' applies
    to the wrong system/ROM, we parse the IPS records to estimate the minimum ROM size
    the patch touches (max offset+len). If the patch includes a standard truncate size
    (3 bytes after EOF), that is returned as trunc_size.
    """
    try:
        with open(patch_file_path, 'rb') as f:
            data = f.read()
    except Exception:
        return (0, None)

    if not data.startswith(b'PATCH'):
        return (0, None)

    i = 5
    max_end = 0
    # records until 'EOF'
    while i + 3 <= len(data):
        if data[i:i+3] == b'EOF':
            i += 3
            break
        if i + 5 > len(data):
            break
        offset = int.from_bytes(data[i:i+3], 'big'); i += 3
        size = int.from_bytes(data[i:i+2], 'big'); i += 2
        if size == 0:
            if i + 3 > len(data):
                break
            rle_size = int.from_bytes(data[i:i+2], 'big'); i += 2
            i += 1  # value
            end = offset + rle_size
        else:
            i += size
            end = offset + size
        if end > max_end:
            max_end = end

    trunc_size = None
    # Standard IPS: optional 3-byte truncate size AFTER EOF.
    rem = data[i:] if i <= len(data) else b''
    if len(rem) == 3:
        try:
            trunc_size = int.from_bytes(rem, 'big')
        except Exception:
            trunc_size = None
    return (max_end, trunc_size)


def bulk_patches_root(script_dir: str) -> str:
    """Return the absolute path to the ./bulk patching folder (next to the app)."""
    try:
        return os.path.join(script_dir, "bulk patching")
    except Exception:
        return os.path.abspath("bulk patching")



def ensure_bulk_folders(script_dir: str, log) -> Tuple[str, str, str, str]:
    """Ensure ./bulk patching/ folder layout exists.

    Layout:
      ./bulk patching/
          patch files/   (put .bps/.ips here)
          base roms/     (put clean base ROMs here)
          output/        (patched ROMs are written here)

    Returns (bulk_root, patch_files_dir, base_roms_dir, output_dir).
    """
    bulk_root = bulk_patches_root(script_dir)
    patch_files_dir = os.path.join(bulk_root, "patch files")
    base_roms_dir = os.path.join(bulk_root, "base roms")
    output_dir = os.path.join(bulk_root, "output")

    # Detect what is missing BEFORE creating anything (so we can tell the user).
    existed_root = os.path.isdir(bulk_root)
    existed_patch = os.path.isdir(patch_files_dir)
    existed_base = os.path.isdir(base_roms_dir)
    existed_out = os.path.isdir(output_dir)

    try:
        os.makedirs(patch_files_dir, exist_ok=True)
        os.makedirs(base_roms_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        try:
            log(f"Bulk Patching - folder create error: {e}")
        except Exception:
            pass
        return bulk_root, patch_files_dir, base_roms_dir, output_dir

    # Log missing folders AFTER creation (so paths definitely exist).
    try:
        if not existed_root:
            log("Bulk patching folder was not found.")
            log(f"Created folder: {bulk_root}")
        if not existed_patch:
            log("Bulk patching folder was not found.")
            log(f"Created folder: {patch_files_dir}")
        if not existed_base:
            log("Bulk patching folder was not found.")
            log(f"Created folder: {base_roms_dir}")
        if not existed_out:
            log("Bulk patching folder was not found.")
            log(f"Created folder: {output_dir}")
    except Exception:
        pass

    return bulk_root, patch_files_dir, base_roms_dir, output_dir

def collect_patches(patch_files_dir: str, log) -> List[str]:
    """Collect all .bps/.ips patch files in patch_files_dir (non-recursive)."""
    out: List[str] = []
    try:
        for name in os.listdir(patch_files_dir):
            full = os.path.join(patch_files_dir, name)
            if not os.path.isfile(full):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in {".bps", ".ips"}:
                out.append(os.path.abspath(full))
    except Exception as e:
        try:
            log(f"Bulk Patching - patch scan error: {e}")
        except Exception:
            pass
    out.sort()
    return out


def collect_baseroms(base_roms_dir: str, log) -> List[str]:
    """Collect ROM files in base_roms_dir (non-recursive)."""
    out: List[str] = []
    seen = set()

    try:
        allowed = set(getattr(rom_byteswap, "FILE_EXTENSIONS", set()))
    except Exception:
        allowed = set()

    def _maybe_add(full_path: str) -> None:
        try:
            if not os.path.isfile(full_path):
                return
            ext = os.path.splitext(full_path)[1].lower()
            if ext in {".bps", ".ips"}:
                return
            if ext in {".json", ".txt"}:
                return
            if allowed and ext not in allowed:
                return
            ap = os.path.abspath(full_path)
            if ap in seen:
                return
            seen.add(ap)
            out.append(ap)
        except Exception:
            return

    try:
        for name in os.listdir(base_roms_dir):
            _maybe_add(os.path.join(base_roms_dir, name))
    except Exception as e:
        try:
            log(f"Bulk Patching - base ROM scan error: {e}")
        except Exception:
            pass

    out.sort()
    return out

def bulk_apply_all(app, script_dir: str, flips_exe_path: str) -> None:
    """Bulk patcher workflow (Auto Patch Files only).

    - Reads every .bps/.ips in ./bulk patching/
    - Reads every ROM in ./bulk patching/base roms/
    - Chooses the correct base ROM per patch (bps by Source CRC32; ips by trial-apply)
    """
    log = getattr(app, "log_message", print)

    bulk_root, patch_files_dir, base_roms_dir, output_dir = ensure_bulk_folders(script_dir, log)

    patch_list = collect_patches(patch_files_dir, log)
    if not patch_list:
        log(f"Bulk Patching - no .bps/.ips files found in: {patch_files_dir}")
        return

    baseroms = collect_baseroms(base_roms_dir, log)
    if not baseroms:
        log(f"Bulk Patching - no base ROMs found in: {base_roms_dir}")
        log("Place your clean ROM(s) into ./bulk patching/base roms/ and patch files into ./bulk patching/patch files/.")
        return

    # Pre-compute CRC32 for every base ROM once, and display utils.py hash info.
    crc_to_base: Dict[str, str] = {}
    for base in baseroms:
        try:
            _log_utils_hashes(log, base, label="Base ROM")
            c = calculate_crc32(base)
            crc_to_base[f"{c:#010x}".lower()] = base
        except Exception as e:
            log(f"Bulk Patching CRC32 read error for {os.path.basename(base)}: {e}")
    log(f"Bulk Patching: found {len(patch_list)} compatible patch file(s). Starting...")

    append_suffix = False
    try:
        append_suffix = bool(app.append_suffix.get())
    except Exception:
        append_suffix = False

    force_patch = False
    try:
        force_patch = bool(app.force_patch.get())
    except Exception:
        force_patch = False

    for patch_file_path in patch_list:
        ext = os.path.splitext(patch_file_path)[1].lower()
        log(f"Bulk Patching - Patch: {os.path.basename(patch_file_path)}")

        if ext == ".bps":
            metadata = get_patch_metadata(patch_file_path)
            if not metadata or "Source CRC32" not in metadata:
                log("  Skipping: could not read Source CRC32 from patch metadata.")
                continue

            # Display patch hash/metadata info (derived from utils.py).
            try:
                log(f"Patch File Hashes ({os.path.basename(patch_file_path)}):")
                for k in ("CRC32", "MD5", "SHA-1", "ZLE", "Source CRC32", "Target CRC32"):
                    if k in metadata:
                        log(f"  {k}: {metadata[k]}")
            except Exception:
                pass

            src_crc = str(metadata.get("Source CRC32", "")).lower()
            chosen_base = crc_to_base.get(src_crc)
            if not chosen_base:
                log(f"  Skipping: no matching base ROM found for Source CRC32 {src_crc}.")
                continue

            try:
                base_ext = os.path.splitext(chosen_base)[1]
                patch_stem = os.path.splitext(os.path.basename(patch_file_path))[0]
                patched_rom_path = os.path.join(output_dir, (patch_stem + "_patched" + base_ext) if append_suffix else (patch_stem + base_ext))

                base_crc32 = calculate_crc32(chosen_base)
                if force_patch and f"{base_crc32:#010x}".lower() != src_crc:
                    command = [flips_exe_path, "--apply", "--ignore-checksum", patch_file_path, chosen_base, patched_rom_path]
                else:
                    command = [flips_exe_path, "--apply", patch_file_path, chosen_base, patched_rom_path]

                subprocess.run(command, check=True, capture_output=True, text=True)

                log(f"  Applied using base ROM: {os.path.basename(chosen_base)}")
                log(f"  Output: {os.path.basename(patched_rom_path)}")

                try:
                    patched_rom_path = _bulk_postprocess(app, patched_rom_path, log)
                except Exception:
                    pass
                try:
                    remember = getattr(app, "_remember_base_rom_for_patch", None)
                    if callable(remember):
                        remember(patch_file_path, chosen_base)
                except Exception:
                    pass
                _bulk_launch_emulator_if_configured(app, patched_rom_path, log)

            except subprocess.CalledProcessError as e:
                log("  Error applying patch:")
                try:
                    log(f"    Command: {' '.join(command)}")
                except Exception:
                    pass
                log(f"    Stdout: {(e.stdout or '').strip() or 'No output'}")
                log(f"    Stderr: {(e.stderr or '').strip() or 'Unknown error occurred.'}")
            except Exception as e:
                log(f"  Bulk apply error: {e}")

        elif ext == ".ips":
            # IPS doesn't embed Source CRC32 in the same way; still show patch hashes via utils.py.
            try:
                _log_utils_hashes(log, patch_file_path, label="IPS Patch File")
            except Exception:
                pass
            applied = False
            # Heuristic: IPS does not embed a source CRC. Prefer base ROMs whose file size
            # best matches what the IPS patch touches (reduces accidental matches).
            ips_min_size, ips_trunc_size, ips_record_count = get_ips_requirements(patch_file_path)
            try:
                if ips_min_size:
                    log(f"  IPS requirements: min_size={ips_min_size} bytes" + (f", trunc={ips_trunc_size} bytes" if ips_trunc_size else "") + (f", records={ips_record_count}" if ips_record_count else ""))
            except Exception:
                pass
            sized = []
            for _cand in baseroms:
                try:
                    sized.append((os.path.getsize(_cand), _cand))
                except Exception:
                    sized.append((0, _cand))
            # Filter to those large enough for the patch.
            filtered = [p for (sz, p) in sorted(sized, key=lambda t: t[0]) if (ips_min_size == 0 or sz >= ips_min_size)]
            # If a standard truncate size is present, prefer exact size matches first.
            if ips_trunc_size and ips_trunc_size > 0:
                exact = [p for (sz, p) in sorted(sized, key=lambda t: t[0]) if sz == ips_trunc_size]
                if exact:
                    filtered = exact + [p for p in filtered if p not in exact]
            ips_candidates = filtered if filtered else baseroms

            for candidate in ips_candidates:
                patched_rom_path = ""
                try:
                    base_ext = os.path.splitext(candidate)[1]
                    patch_stem = os.path.splitext(os.path.basename(patch_file_path))[0]
                    patched_rom_path = os.path.join(output_dir, (patch_stem + "_patched" + base_ext) if append_suffix else (patch_stem + base_ext))

                    if force_patch:
                        command = [flips_exe_path, "--apply", "--ignore-checksum", patch_file_path, candidate, patched_rom_path]
                    else:
                        command = [flips_exe_path, "--apply", patch_file_path, candidate, patched_rom_path]

                    subprocess.run(command, check=True, capture_output=True, text=True)

                    log(f"  Applied using base ROM: {os.path.basename(candidate)}")
                    log(f"  Output: {os.path.basename(patched_rom_path)}")

                    try:
                        patched_rom_path = _bulk_postprocess(app, patched_rom_path, log)
                    except Exception:
                        pass
                    _bulk_launch_emulator_if_configured(app, patched_rom_path, log)

                    applied = True
                    break

                except subprocess.CalledProcessError:
                    try:
                        if patched_rom_path and os.path.exists(patched_rom_path):
                            os.remove(patched_rom_path)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    log(f"  Bulk apply error: {e}")
                    break

            if not applied:
                log("  Skipping: could not apply this .ips patch to any base ROM in baseroms/.")

        else:
            log("  Skipping: not a .bps/.ips file.")

    log("Bulk Patching: done.")
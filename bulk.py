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
import tempfile
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
    validate_ips_base_rom,
    log_operation_paths,
    format_log_field,
    has_ines_header,
    has_snes_copier_header,
    remove_ines_header_bytes,
    add_ines_header_bytes,
    add_snes_copier_header_bytes,
    remove_snes_copier_header_bytes,
    normalize_rom_extension,
    get_known_header_info,
    can_add_snes_copier_header,
    get_rom_family_display,
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


def _bulk_prepare_patch_io_context(app, patch_file_path: str, base_rom_path: str, final_output_path: str, log: Callable[[str], None]) -> dict:
    """Prepare temporary input/output files for ROM Header Options automate modes.

    Rules:
    - Bulk patching must keep working normally when no ROM Header Option is selected.
    - Options 3 and 6 enhance bulk mode; they must never block it.
    - If no matching header is found, continue patching normally and add the
      matching header to the output afterward.
    """
    context = {
        "input_rom_path": base_rom_path,
        "temp_input_rom_path": None,
        "working_output_path": final_output_path,
        "temp_output_path": None,
        "restore_output_header": b"",
        "restore_output_header_label": "",
    }

    with open(base_rom_path, "rb") as f:
        base_data = f.read()

    patch_name = os.path.basename(patch_file_path)
    base_name = os.path.basename(base_rom_path)
    suffix = os.path.splitext(base_rom_path)[1]
    base_ext = normalize_rom_extension(base_rom_path)

    try:
        temp_remove_ines = bool(app.temp_remove_ines_header.get())
    except Exception:
        temp_remove_ines = False
    try:
        temp_remove_snes = bool(app.temp_remove_snes_header.get())
    except Exception:
        temp_remove_snes = False

    if temp_remove_ines and base_ext == "nes":
        log(f"ROM header options: Checking Base ROM for temporary iNES header removal before applying {patch_name}.")
        header_info = get_known_header_info(base_data, base_rom_path)
        if header_info and header_info.get("name") == "iNES":
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
                tmp_in.write(remove_ines_header_bytes(base_data, ext_or_path=base_rom_path))
                context["temp_input_rom_path"] = tmp_in.name
                context["input_rom_path"] = tmp_in.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_out:
                context["temp_output_path"] = tmp_out.name
                context["working_output_path"] = tmp_out.name
            context["restore_output_header"] = bytes(base_data[:header_info["size"]])
            context["restore_output_header_label"] = "iNES"
            log(f"Removed iNES header temporarily for patch input: {base_name}")
        else:
            log(f"No iNES header found on Base ROM: {base_name}")
            log(f"No iNES header to remove; will add iNES copier header to output after patching: {os.path.basename(final_output_path)}")
            log("")

    elif temp_remove_snes and base_ext in {"sfc", "smc", "swc", "fig"}:
        log(f"ROM header options: Checking Base ROM for temporary SNES copier header removal before applying {patch_name}.")
        if has_snes_copier_header(base_data, ext_or_path=base_rom_path):
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
                tmp_in.write(remove_snes_copier_header_bytes(base_data, ext_or_path=base_rom_path))
                context["temp_input_rom_path"] = tmp_in.name
                context["input_rom_path"] = tmp_in.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_out:
                context["temp_output_path"] = tmp_out.name
                context["working_output_path"] = tmp_out.name
            context["restore_output_header"] = bytes(base_data[:512])
            context["restore_output_header_label"] = "SNES copier"
            log(f"Removed SNES copier header temporarily for patch input: {base_name}")
        else:
            log(f"No SNES copier header found on Base ROM: {base_name}")
            log(f"No SNES copier header to remove; will add SNES copier header to output after patching: {os.path.basename(final_output_path)}")
            log("")

    return context


def _bulk_finalize_patch_output(context: dict, final_output_path: str, log: Callable[[str], None]) -> str:
    """Finalize any temp-output workflow and restore removed header when needed."""
    working_output_path = context.get("working_output_path") or final_output_path
    if os.path.abspath(working_output_path) == os.path.abspath(final_output_path):
        return final_output_path

    with open(working_output_path, "rb") as f:
        patched_data = f.read()

    restore_output_header = context.get("restore_output_header") or b""
    restore_output_header_label = str(context.get("restore_output_header_label") or "").strip()
    output_name = os.path.basename(final_output_path)

    if restore_output_header:
        patched_data = restore_output_header + patched_data
        if restore_output_header_label == "iNES":
            log(f"Restored iNES header to patched output: {output_name}")
        elif restore_output_header_label == "SNES copier":
            log(f"Added SNES copier header to patched output: {output_name}")
        else:
            log(f"Restored header to patched output: {output_name}")

    with open(final_output_path, "wb") as f:
        f.write(patched_data)
    return final_output_path

def _bulk_apply_output_header_options(app, patched_rom_path: str, base_rom_path: str, context: dict, log: Callable[[str], None]) -> str:
    base_ext = normalize_rom_extension(base_rom_path)
    output_name = os.path.basename(patched_rom_path)

    if base_ext == "nes":
        add_out = bool(app.temp_remove_ines_header.get() or app.add_ines_header.get())
        remove_out = bool(app.remove_ines_header.get())
        if add_out and remove_out:
            log(f"Conflicting NES output options; leaving output unchanged: {output_name}")
            return patched_rom_path
        if remove_out:
            try:
                with open(patched_rom_path, "rb") as f:
                    data = f.read()
                updated = remove_ines_header_bytes(data, patched_rom_path)
                if updated != data:
                    with open(patched_rom_path, "wb") as f:
                        f.write(updated)
                    log(f"Removed iNES header from output: {output_name}")
            except Exception as e:
                log(f"Failed to remove iNES header from output: {e}")
        elif add_out:
            try:
                with open(patched_rom_path, "rb") as f:
                    data = f.read()
                updated = add_ines_header_bytes(data, header_bytes=(context.get("restore_output_header") or context.get("restore_ines_header") or (b"NES\x1a" + (b"\x00" * 12))), ext_or_path=patched_rom_path)
                if updated != data:
                    with open(patched_rom_path, "wb") as f:
                        f.write(updated)
                    log(f"Added iNES copier header to output: {output_name}")
            except Exception as e:
                log(f"Failed to add iNES copier header to output: {e}")

    elif base_ext in {"sfc", "smc", "swc", "fig"}:
        add_out = bool(app.temp_remove_snes_header.get() or app.add_snes_header.get())
        remove_out = bool(app.remove_snes_header.get())
        if add_out and remove_out:
            log(f"Conflicting SNES output options; leaving output unchanged: {output_name}")
            return patched_rom_path
        if remove_out:
            try:
                with open(patched_rom_path, "rb") as f:
                    data = f.read()
                updated = remove_snes_copier_header_bytes(data, patched_rom_path)
                if updated != data:
                    with open(patched_rom_path, "wb") as f:
                        f.write(updated)
                    log(f"Removed SNES copier header from output: {output_name}")
            except Exception as e:
                log(f"Failed to remove SNES copier header from output: {e}")
        elif add_out:
            try:
                with open(patched_rom_path, "rb") as f:
                    data = f.read()
                updated = add_snes_copier_header_bytes(data, ext_or_path=patched_rom_path)
                if updated != data:
                    with open(patched_rom_path, "wb") as f:
                        f.write(updated)
                    log(f"Added SNES copier header to output: {output_name}")
            except Exception as e:
                log(f"Failed to add SNES copier header to output: {e}")

    return patched_rom_path


def _bulk_postprocess(app, patched_rom_path: str, base_rom_path: str, log: Callable[[str], None]) -> str:
    """_bulk_postprocess helper.

    Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
    """
    patched_rom_path = _bulk_apply_byteswap_to_output(app, patched_rom_path, log)
    patched_rom_path = _bulk_apply_trim_to_64mb_output(app, patched_rom_path, log)
    return patched_rom_path


def _bulk_launch_emulator_if_configured(app, patched_rom_path: str, log: Callable[[str], None]) -> None:
    """_bulk_launch_emulator_if_configured helper.

    Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
    """
    try:
        launcher = getattr(app, "launch_emulator_if_configured", None)
        if callable(launcher):
            launcher(patched_rom_path)
    except Exception as e:
        try:
            log(f"Emulator launch error: {e}")
        except Exception:
            pass


def _bulk_get_emulator_for_rom(app, rom_path: str) -> Tuple[str, str]:
    """Return the configured emulator path and matched rule for a ROM path."""
    try:
        if app.association_action.get() != "run_emulator":
            return ("", "")
    except Exception:
        return ("", "")

    try:
        rom_ext = str(os.path.splitext(str(rom_path))[1] or "").strip().lower()
        if rom_ext.startswith('.'):
            rom_ext = rom_ext[1:]
    except Exception:
        rom_ext = ""

    assignments = list(getattr(app, "emulator_assignments", []) or [])
    emulator = ""
    matched_rule = ""
    wildcard_emulator = ""
    wildcard_rule = ""

    normalize = getattr(app, "_normalize_rom_type_text", None)
    parse = getattr(app, "_parse_rom_type_tokens", None)
    fmt = getattr(app, "_format_rom_type_tokens", None)

    def _normalize(value):
        if callable(normalize):
            try:
                return str(normalize(value) or "")
            except Exception:
                pass
        value = str(value or "").strip().lower()
        return value[1:] if value.startswith('.') else value

    def _parse(value):
        if callable(parse):
            try:
                return list(parse(value) or [])
            except Exception:
                pass
        if isinstance(value, (list, tuple, set)):
            raw_tokens = value
        else:
            raw_tokens = str(value or "").replace(';', ',').split(',')
        seen = set()
        ordered = []
        for token in raw_tokens:
            norm = _normalize(token)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            ordered.append(norm)
        return ordered

    def _format(value):
        if callable(fmt):
            try:
                return str(fmt(value) or "")
            except Exception:
                pass
        return ", ".join(_parse(value))

    rom_ext = _normalize(rom_ext)

    for item in assignments:
        emu_path = os.path.abspath(str(item.get("path") or "").strip())
        if not emu_path:
            continue

        rule_text = str(item.get("rom_type") or "").strip().lower()
        tokens = _parse(rule_text)

        if not tokens:
            if not wildcard_emulator:
                wildcard_emulator = emu_path
                wildcard_rule = rule_text
            continue

        if rom_ext and rom_ext in tokens:
            emulator = emu_path
            matched_rule = _format(tokens)
            break

    if not emulator and wildcard_emulator:
        emulator = wildcard_emulator
        matched_rule = wildcard_rule

    if not emulator and not assignments:
        try:
            emulator = os.path.abspath(str(app.emulator_path.get() or "").strip())
            matched_rule = rom_ext or ""
        except Exception:
            emulator = ""
            matched_rule = ""

    return (emulator, matched_rule)


def _bulk_predict_final_output_path(app, output_dir: str, patch_file_path: str, base_rom_path: str, append_suffix: bool) -> str:
    """Predict the final output ROM path for launch-summary logging."""
    base_ext = os.path.splitext(base_rom_path)[1]
    patch_stem = os.path.splitext(os.path.basename(patch_file_path))[0]
    out_path = os.path.join(output_dir, (patch_stem + "_patched" + base_ext) if append_suffix else (patch_stem + base_ext))

    try:
        mode = _bulk_get_byteswap_mode(app)
    except Exception:
        mode = "disable"

    if mode in ("z64", "n64", "v64"):
        ext = os.path.splitext(out_path)[1].lower()
        if ext in {".z64", ".n64", ".v64"}:
            out_path = os.path.splitext(out_path)[0] + f".{mode}"

    return out_path


def _bulk_log_emulator_launch_summary(app, runnable_patches, compatibility_info, baseroms, output_dir, append_suffix, log) -> None:
    """Log how many ROMs are expected to launch in each emulator."""
    launch_counts: Dict[str, int] = {}

    for patch_file_path in runnable_patches:
        ext = os.path.splitext(patch_file_path)[1].lower()
        predicted_output = ""

        if ext == ".bps":
            patch_info = compatibility_info.get(patch_file_path, {})
            metadata = patch_info.get("metadata") or get_patch_metadata(patch_file_path) or {}
            src_crc = str(metadata.get("Source CRC32", "")).lower()
            chosen_base = patch_info.get("chosen_base")
            if not chosen_base and src_crc:
                for candidate in baseroms:
                    try:
                        if f"{calculate_crc32(candidate):#010x}".lower() == src_crc:
                            chosen_base = candidate
                            break
                    except Exception:
                        continue
            if not chosen_base and baseroms:
                try:
                    if bool(app.force_patch.get()):
                        chosen_base = baseroms[0]
                except Exception:
                    pass
            if not chosen_base:
                continue
            predicted_output = _bulk_predict_final_output_path(app, output_dir, patch_file_path, chosen_base, append_suffix)

        elif ext == ".ips":
            patch_info = compatibility_info.get(patch_file_path, {})
            validated_candidates = list(patch_info.get("validated_candidates", []))
            candidate = validated_candidates[0][1] if validated_candidates else ""
            if not candidate:
                try:
                    if bool(app.force_patch.get()) and baseroms:
                        candidate = baseroms[0]
                except Exception:
                    pass
            if not candidate:
                continue
            predicted_output = _bulk_predict_final_output_path(app, output_dir, patch_file_path, candidate, append_suffix)

        if not predicted_output:
            continue

        emulator_path, _matched_rule = _bulk_get_emulator_for_rom(app, predicted_output)
        if not emulator_path:
            continue
        launch_counts[emulator_path] = launch_counts.get(emulator_path, 0) + 1

    if not launch_counts:
        log("Bulk Patching: No ROMs are configured to auto-launch with an emulator.")
        return

    log("---- Emulator Launch Summary ----")
    for emulator_path, count in sorted(launch_counts.items(), key=lambda kv: os.path.basename(kv[0]).lower()):
        log(f"{count} ROM(s) running in {os.path.basename(emulator_path)}")
    log("--------------------------------")


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
        log(format_log_field("CRC32", f"{crc32:#010x}"))
        log(format_log_field("MD5", md5))
        log(format_log_field("SHA-1", sha1))
        log(format_log_field("ZLE", zle))
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

def collect_patches(patch_files_dir: str, log, *, recursive: bool = False, include_ips: bool = False) -> List[str]:
    """Collect supported patch files in patch_files_dir.

    Bulk mode treats the scope menu like this:
      - search_scope == "enable"    -> recursive scan (subfolders too)
      - search_scope == "directory" -> top-level folder only
      - search_scope == "disable"   -> also top-level folder only

    The last case intentionally preserves the existing bulk behavior so
    "Disable expanded file search" is effectively ignored while bulk patching
    is enabled.
    """
    out: List[str] = []
    seen = set()

    def _maybe_add(full_path: str) -> None:
        """_maybe_add helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
        try:
            if not os.path.isfile(full_path):
                return
            ext = os.path.splitext(full_path)[1].lower()
            allowed_patch_exts = {".bps"} | ({".ips"} if include_ips else set())
            if ext not in allowed_patch_exts:
                return
            ap = os.path.abspath(full_path)
            if ap in seen:
                return
            seen.add(ap)
            out.append(ap)
        except Exception:
            return

    try:
        if recursive:
            for root, _, files in os.walk(patch_files_dir):
                for name in files:
                    _maybe_add(os.path.join(root, name))
        else:
            for name in os.listdir(patch_files_dir):
                _maybe_add(os.path.join(patch_files_dir, name))
    except Exception as e:
        try:
            log(f"Bulk Patching - patch scan error: {e}")
        except Exception:
            pass
    out.sort()
    return out


def collect_baseroms(base_roms_dir: str, log, *, recursive: bool = False) -> List[str]:
    """Collect ROM files in base_roms_dir.

    In bulk mode, recursive=True means search subfolders too. Any other bulk
    scope continues to scan only the top-level base roms folder.
    """
    out: List[str] = []
    seen = set()

    try:
        allowed = set(getattr(rom_byteswap, "FILE_EXTENSIONS", set()))
    except Exception:
        allowed = set()

    def _maybe_add(full_path: str) -> None:
        """_maybe_add helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
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
        if recursive:
            for root, _, files in os.walk(base_roms_dir):
                for name in files:
                    _maybe_add(os.path.join(root, name))
        else:
            for name in os.listdir(base_roms_dir):
                _maybe_add(os.path.join(base_roms_dir, name))
    except Exception as e:
        try:
            log(f"Bulk Patching - base ROM scan error: {e}")
        except Exception:
            pass

    out.sort()
    return out

def prevalidate_bulk_patches(patch_list: List[str], baseroms: List[str], crc_to_base: Dict[str, str], force_patch: bool) -> Tuple[List[str], Dict[str, dict]]:
    """Return only runnable bulk patches plus lightweight compatibility info.

    This keeps bad IPS/BPS files out of the main processing loop so the UI only
    shows patches that can actually run with the currently loaded base ROMs.
    """
    runnable: List[str] = []
    info: Dict[str, dict] = {}

    for patch_file_path in patch_list:
        ext = os.path.splitext(patch_file_path)[1].lower()
        patch_info = {'ext': ext}

        if ext == '.bps':
            metadata = get_patch_metadata(patch_file_path) or {}
            src_crc = str(metadata.get('Source CRC32', '')).lower()
            chosen_base = crc_to_base.get(src_crc)
            if chosen_base or force_patch:
                patch_info.update({'metadata': metadata, 'chosen_base': chosen_base, 'source_crc': src_crc})
                runnable.append(patch_file_path)
                info[patch_file_path] = patch_info
            continue

        if ext == '.ips':
            min_size, trunc_size, record_count = get_ips_requirements(patch_file_path)
            validated_candidates = []
            for candidate in baseroms:
                ok, reason, details = validate_ips_base_rom(patch_file_path, candidate)
                if ok:
                    validated_candidates.append((details.get('rom_size', 0), candidate, details))

            validated_candidates.sort(key=lambda t: t[0])
            if validated_candidates or force_patch:
                patch_info.update({
                    'ips_min_size': min_size,
                    'ips_trunc_size': trunc_size,
                    'ips_record_count': record_count,
                    'validated_candidates': validated_candidates,
                })
                runnable.append(patch_file_path)
                info[patch_file_path] = patch_info
            continue

    return runnable, info


def bulk_apply_all(app, script_dir: str, flips_exe_path: str) -> None:
    """Bulk patcher workflow (Auto Patch Files only).

    - Reads every .bps/.ips in ./bulk patching/
    - Reads every ROM in ./bulk patching/base roms/
    - Chooses the correct base ROM per patch (bps by Source CRC32; ips by trial-apply)
    """
    log = getattr(app, "log_message", print)

    bulk_root, patch_files_dir, base_roms_dir, output_dir = ensure_bulk_folders(script_dir, log)

    try:
        scope = str(app.search_scope.get()).strip().lower()
    except Exception:
        scope = "disable"
    recursive_scan = (scope == "enable")

    try:
        include_ips = bool(app.bulk_enable_ips.get())
    except Exception:
        include_ips = False

    patch_list = collect_patches(patch_files_dir, log, recursive=recursive_scan, include_ips=include_ips)
    if not patch_list:
        if recursive_scan:
            log(f"Bulk Patching - no supported patch files found in: {patch_files_dir} (including subfolders)")
        else:
            log(f"Bulk Patching - no supported patch files found in: {patch_files_dir}")
        return

    if not include_ips:
        log("Bulk Patching: IPS patch scanning is disabled in Settings > Bulk Patching.")

    baseroms = collect_baseroms(base_roms_dir, log, recursive=recursive_scan)
    if not baseroms:
        log(f"Bulk Patching - no base ROMs found in: {base_roms_dir}")
        log("Place your clean ROM(s) into ./bulk patching/base roms/ and patch files into ./bulk patching/patch files/.")
        return

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

    # Pre-compute CRC32 for every base ROM once, and display utils.py hash info.
    crc_to_base: Dict[str, str] = {}
    base_crc_by_path: Dict[str, str] = {}
    for base in baseroms:
        try:
            _log_utils_hashes(log, base, label="Base ROM")
            c = calculate_crc32(base)
            crc_text = f"{c:#010x}".lower()
            crc_to_base[crc_text] = base
            base_crc_by_path[base] = crc_text
        except Exception as e:
            log(f"Bulk Patching CRC32 read error for {os.path.basename(base)}: {e}")

    runnable_patches, compatibility_info = prevalidate_bulk_patches(
        patch_list, baseroms, crc_to_base, force_patch
    )
    if not runnable_patches:
        log("Bulk Patching: no patch files matched the available base ROMs.")
        return

    log(f"Bulk Patching: found {len(runnable_patches)} compatible patch file(s). Starting...")
    try:
        _bulk_log_emulator_launch_summary(app, runnable_patches, compatibility_info, baseroms, output_dir, append_suffix, log)
    except Exception as e:
        log(f"Bulk Patching: emulator launch summary error: {e}")

    for patch_file_path in runnable_patches:
        ext = os.path.splitext(patch_file_path)[1].lower()
        log(f"Bulk Patching: Patched → {os.path.basename(patch_file_path)}")

        if ext == ".bps":
            patch_info = compatibility_info.get(patch_file_path, {})
            metadata = patch_info.get("metadata") or get_patch_metadata(patch_file_path)
            if not metadata or "Source CRC32" not in metadata:
                log("  Skipping: could not read Source CRC32 from patch metadata.")
                continue

            # Display patch hash/metadata info (derived from utils.py).
            try:
                log(f"BPS Patch File Hashes ({os.path.basename(patch_file_path)}):")
                for k in ("CRC32", "MD5", "SHA-1", "ZLE", "Source CRC32", "Target CRC32"):
                    if k in metadata:
                        log(format_log_field(k, metadata[k]))
            except Exception:
                pass

            src_crc = str(metadata.get("Source CRC32", "")).lower()
            chosen_base = patch_info.get("chosen_base") or crc_to_base.get(src_crc)
            if chosen_base:
                try:
                    family = get_rom_family_display(chosen_base)
                except Exception:
                    family = ""
                if family:
                    log(format_log_field("Family", family))
            if not chosen_base and not force_patch:
                log(f"  Skipping: no matching base ROM found for Source CRC32 {src_crc}.")
                continue
            if not chosen_base and force_patch and baseroms:
                chosen_base = baseroms[0]

            temp_input_rom_path = None
            temp_output_path = None
            try:
                base_ext = os.path.splitext(chosen_base)[1]
                patch_stem = os.path.splitext(os.path.basename(patch_file_path))[0]
                patched_rom_path = os.path.join(output_dir, (patch_stem + "_patched" + base_ext) if append_suffix else (patch_stem + base_ext))
                context = _bulk_prepare_patch_io_context(app, patch_file_path, chosen_base, patched_rom_path, log)
                input_rom_path = context['input_rom_path']
                temp_input_rom_path = context.get('temp_input_rom_path')
                temp_output_path = context.get('temp_output_path')
                working_output_path = context['working_output_path']

                input_crc_text = ""
                try:
                    input_crc_text = f"{calculate_crc32(input_rom_path):#010x}".lower()
                except Exception:
                    input_crc_text = base_crc_by_path.get(chosen_base, "")

                if force_patch and input_crc_text != src_crc:
                    command = [flips_exe_path, "--apply", "--ignore-checksum", patch_file_path, input_rom_path, working_output_path]
                else:
                    command = [flips_exe_path, "--apply", patch_file_path, input_rom_path, working_output_path]

                subprocess.run(command, check=True, capture_output=True, text=True)
                patched_rom_path = _bulk_finalize_patch_output(context, patched_rom_path, log)

                try:
                    patched_rom_path = _bulk_postprocess(app, patched_rom_path, chosen_base, log)
                except Exception as e:
                    log(f"Post-process error: {e}")

                log_operation_paths(
                    log,
                    patch_file_path=patch_file_path,
                    base_rom_path=input_rom_path,
                    output_file_path=patched_rom_path
                )

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
            finally:
                for temp_path in (temp_input_rom_path, temp_output_path):
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

        elif ext == ".ips":
            patch_info = compatibility_info.get(patch_file_path, {})
            try:
                meta = get_ips_metadata(patch_file_path) or {}
                log(f"IPS Patch File Hashes ({os.path.basename(patch_file_path)}):")
                for k in ("CRC32", "MD5", "SHA-1", "ZLE", "Min Required Size", "Record Count", "RLE Records", "Data Records", "Max Offset", "Truncate Size", "RLE Output Bytes", "IPS Warning"):
                    if k in meta:
                        log(format_log_field(k, meta[k]))
            except Exception:
                pass

            applied = False
            validated_candidates = list(patch_info.get("validated_candidates", []))


            if not validated_candidates and force_patch:
                log("  Force to Patch enabled. IPS structural checks are being bypassed for bulk mode.")
                validated_candidates = []
                for candidate in baseroms:
                    try:
                        validated_candidates.append((os.path.getsize(candidate), candidate, {}))
                    except Exception:
                        validated_candidates.append((0, candidate, {}))
                validated_candidates.sort(key=lambda t: t[0])

            for _size, candidate, _details in validated_candidates:
                patched_rom_path = ""
                temp_input_rom_path = None
                temp_output_path = None
                try:
                    base_ext = os.path.splitext(candidate)[1]
                    patch_stem = os.path.splitext(os.path.basename(patch_file_path))[0]
                    patched_rom_path = os.path.join(output_dir, (patch_stem + "_patched" + base_ext) if append_suffix else (patch_stem + base_ext))
                    context = _bulk_prepare_patch_io_context(app, patch_file_path, candidate, patched_rom_path, log)
                    input_rom_path = context['input_rom_path']
                    temp_input_rom_path = context.get('temp_input_rom_path')
                    temp_output_path = context.get('temp_output_path')
                    working_output_path = context['working_output_path']

                    if force_patch:
                        command = [flips_exe_path, "--apply", "--ignore-checksum", patch_file_path, input_rom_path, working_output_path]
                    else:
                        command = [flips_exe_path, "--apply", patch_file_path, input_rom_path, working_output_path]

                    subprocess.run(command, check=True, capture_output=True, text=True)
                    patched_rom_path = _bulk_finalize_patch_output(context, patched_rom_path, log)

                    try:
                        patched_rom_path = _bulk_postprocess(app, patched_rom_path, candidate, log)
                    except Exception as e:
                        log(f"Post-process error: {e}")

                    log_operation_paths(
                        log,
                        patch_file_path=patch_file_path,
                        base_rom_path=input_rom_path,
                        output_file_path=patched_rom_path,
                        header="  Applied using:",
                    )
                    _bulk_launch_emulator_if_configured(app, patched_rom_path, log)

                    applied = True
                    break

                except subprocess.CalledProcessError:
                    try:
                        failed_output = working_output_path if 'working_output_path' in locals() else patched_rom_path
                        if failed_output and os.path.exists(failed_output):
                            os.remove(failed_output)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    log(f"  Bulk apply error: {e}")
                    break
                finally:
                    for temp_path in (temp_input_rom_path, temp_output_path):
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass

            if not applied:
                log("  Skipping: could not apply this .ips patch to any valid base ROM in baseroms/.")

        else:
            log("  Skipping: not a .bps/.ips file.")

    log("Bulk Patching: done.")
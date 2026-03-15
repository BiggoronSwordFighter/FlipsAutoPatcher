import os
import binascii
import hashlib
import struct
import base64
import re

# Function to calculate CRC32 of a file
def calculate_crc32(file_path):
    crc32 = 0
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            crc32 = binascii.crc32(chunk, crc32)
    return crc32 & 0xFFFFFFFF

# Function to calculate MD5 of a file
def calculate_md5(file_path):
    md5_hash = hashlib.md5()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

# Function to calculate SHA-1 of a file
def calculate_sha1(file_path):
    sha1_hash = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            sha1_hash.update(chunk)
    return sha1_hash.hexdigest()

# Function to calculate the ZLE hash
def calculate_zle_hash(file_path):
    with open(file_path, 'rb') as f:
        rom_content = f.read()
    zle_value = rom_content[16:28]
    return zle_value.hex().rstrip('0')

# Function to retrieve metadata from a .bps patch file
def get_patch_metadata(patch_file_path):
    try:
        with open(patch_file_path, 'rb') as f:
            crc32 = calculate_crc32(patch_file_path)
            md5 = calculate_md5(patch_file_path)
            sha1 = calculate_sha1(patch_file_path)
            zle = calculate_zle_hash(patch_file_path)
            f.seek(-12, os.SEEK_END)
            source_crc32, target_crc32 = struct.unpack('<II', f.read(8))
            return {
                "CRC32": f"{crc32:#010x}",
                "MD5": md5,
                "SHA-1": sha1,
                "ZLE": zle,
                "Source CRC32": f"{source_crc32:#010x}",
                "Target CRC32": f"{target_crc32:#010x}"
            }
    except Exception as e:
        print(f"Error reading patch file {patch_file_path}: {e}")
        return None


# ------------------------------
# IPS helpers (no embedded CRC32)
# ------------------------------
# IPS format: b"PATCH" + records + b"EOF" + optional 3-byte truncate size.
# IPS does NOT store a source/target CRC32. We can only derive structural requirements:
#   - minimum required input size (highest byte touched + 1)
#   - optional truncate size (3 bytes after EOF), if present

def get_ips_requirements(patch_file_path):
    """Return (min_required_size_bytes, truncate_size_bytes_or_None, record_count)."""
    try:
        with open(patch_file_path, "rb") as f:
            data = f.read()
    except Exception:
        return (0, None, 0)

    if not data.startswith(b"PATCH"):
        return (0, None, 0)

    i = 5
    max_end = 0
    record_count = 0

    while i + 3 <= len(data):
        if data[i:i+3] == b"EOF":
            i += 3
            break

        if i + 5 > len(data):
            break

        offset = int.from_bytes(data[i:i+3], "big")
        i += 3
        size = int.from_bytes(data[i:i+2], "big")
        i += 2
        record_count += 1

        if size == 0:
            if i + 3 > len(data):
                break
            rle_size = int.from_bytes(data[i:i+2], "big")
            i += 2
            i += 1  # value byte
            end = offset + rle_size
        else:
            if i + size > len(data):
                break
            i += size
            end = offset + size

        if end > max_end:
            max_end = end

    trunc_size = None
    rem = data[i:]
    if len(rem) == 3:
        try:
            trunc_size = int.from_bytes(rem, "big")
        except Exception:
            trunc_size = None

    return (max_end, trunc_size, record_count)


def get_ips_metadata(patch_file_path):
    """Return a metadata dict for IPS patches (hashes + IPS requirements)."""
    try:
        crc32 = calculate_crc32(patch_file_path)
        md5 = calculate_md5(patch_file_path)
        sha1 = calculate_sha1(patch_file_path)
        zle = calculate_zle_hash(patch_file_path)
        min_size, trunc_size, recs = get_ips_requirements(patch_file_path)

        meta = {
            "CRC32": f"{crc32:#010x}",
            "MD5": md5,
            "SHA-1": sha1,
            "ZLE": zle,
            "Min Required Size": str(int(min_size)),
            "Record Count": str(int(recs)),
        }
        if trunc_size is not None:
            meta["Truncate Size"] = str(int(trunc_size))
        return meta
    except Exception as e:
        print(f"Error reading IPS patch file {patch_file_path}: {e}")
        return None


# ------------------------------
# GUI logging helpers (Tkinter)
# ------------------------------
# Centralized, buffered writer for the Info/Output box.
# - Prevents double-blank-line spam
# - Batches inserts to reduce redraw overhead in bulk operations


class GUILogger:
    """Buffered writer for the Info/Output box."""

    def __init__(self, widget, *, max_lines=6000, flush_ms=25):
        self.widget = widget
        self.max_lines = int(max_lines)
        self.flush_ms = int(flush_ms)
        self._queue = []
        self._scheduled = False
        self._last_blank = False

        # ------------------------------------------------------------------
        # Blank-line rules for the Info/Output box.
        #
        # IMPORTANT:
        # This logger now relies ONLY on explicit keyword matching.
        # There is NO generic header detection here.
        #
        # How it works:
        # - If a line STARTS with any text in _paragraph_prefixes,
        #   insert one blank line BEFORE that line.
        # - If a line CONTAINS any text in _paragraph_contains,
        #   insert one blank line BEFORE that line.
        # - If a line STARTS with any text in _after_blank_prefixes,
        #   insert one blank line AFTER that line.
        # - If a line CONTAINS any text in _after_blank_contains,
        #   insert one blank line AFTER that line.
        #
        # All matching is case-insensitive because each line is converted with
        # .casefold() before checking the keyword lists.
        #
        # TIP FOR FUTURE EDITS:
        # Whenever you add a new log_message(...) anywhere in main.py,
        # open_with_handle.py, or bulk.py, decide whether that new line is:
        #   1) a section opener      -> add it to a BEFORE list
        #   2) a section closer      -> add it to an AFTER list
        #   3) both                  -> add it to both lists
        # ------------------------------------------------------------------

        # Blank lines BEFORE section-style lines.
        self._paragraph_prefixes = (
            # Normal patch/apply flow (main.py)
            "selected patch file:",
            "patch file metadata",
            "patch file hashes",
            "base rom hashes",
            "modified rom hashes",
            "selected modified rom file:",
            "select the base rom file.",
            "select the modified rom.",
            "patching process has started.",
            "patch creation process has started.",
            "patch creation process is complete.",
            "Successfully applied patch",
            "note:",

            # Open-with flow (open_with_handle.py) 
            "opened with patch file:",
            "opened with base rom file:",
            "opened with modified rom file:",
            "select the modified rom file:",
            "no modified rom file selected.",
            "no valid rom or patch file selected.",

            # Bulk mode (bulk.py)
            "bulk patching enabled",
            "bulk patching:",
            "bulk patching -",
            "bulk patching folder was not found.",
            "created folder:",
            "applied using base rom:",
            "output:",

            # Config / general status 
            "config ",
            "no valid modified rom files selected.",
            "Error: Base ROM and Modified ROM cannot be the same file.",

            # Settings button
            "Launched emulator with:",
            "Added emulator:",
            "Removed emulator:",
            "Cleared all emulator assignments.",
            "Registered Windows file types for .bps and .ips.",
            "Cleared .bps/.ips file associations and icon cache.",
            "Icon path:",
            "Open command:",
            "Clearing icon cache in the background...",
        )

        # Optional BEFORE matches for text that may appear in the middle of a line.
        # Kept empty on purpose until you need it.
        self._paragraph_contains = (
             # Normal patch/apply flow (main.py)
            "Force to Patch enabled.",
        )

        # Blank lines AFTER lines that should visually finish a section.
        self._after_blank_prefixes = (

            # Hash/metadata blocks: add a space after the block ends.
            "select the base rom file.",
            "No Base ROM file selected.",

            # Bulk mode (bulk.py)
            "bulk patching -",
            "ips requirements:",
            "endian:",

            # Process markers / section labels.
            "patching process has started.",
            "patch creation process has started.",
            "Proceeding with patch.",
            "patch creation process is complete.",
            "note:",
            "Byte-swap complete",

            # Result / output labels.
            "applied using base rom:",
            "output:",
            "successfully created patch",
            "successfully applied patch",
            "successfully applied patch despite errors",
            "Output file location:",
            "File does not use endian swapping.",
            "Trim skipped:",
            "skipping patching for",
            "skipping patching",
            "skipping ",

            # Open-with markers.
            "opened with patch file:",
            "opened with base rom file:",
            "opened with modified rom file:",

            # Settings button
            "Clearing icon cache in the background...",
            "Cleared .bps/.ips file associations and icon cache.",
            "Icon cache task finished.",
            "Clearing Open With history in the background...",
            "Cleared current-user Open With history for supported patch/app launcher file types.",
            "Context menu cleanup task finished.",
        )

        # Optional AFTER matches for text that may appear in the middle of a line.
        # Kept empty on purpose until you need it.
        self._after_blank_contains = (
        )

    def write(self, message, *, section=None):
        msg = "" if message is None else str(message)

        if section:
            self._enqueue("")
            self._enqueue(f"=== {section} ===")

        self._enqueue(msg)
        self._schedule()

    def _format_line(self, raw: str) -> str:
        raw = raw.rstrip("\n")

        m = re.match(r"^\s*(CRC32|MD5|SHA-1|ZLE|Source CRC32|Target CRC32)\s*:\s*(.*)$", raw)
        if m:
            key, val = m.group(1), m.group(2)
            return f"  {key:<12}: {val}"

        m2 = re.match(r"^\s*IPS requirements:\s*(.*)$", raw, re.IGNORECASE)
        if m2:
            return f"  IPS requirements: {m2.group(1)}"

        return raw

    def _wants_before_blank(self, low: str) -> bool:
        low = "" if low is None else str(low).casefold()
        if any(low.startswith(str(p).casefold()) for p in self._paragraph_prefixes):
            return True
        return any(str(token).casefold() in low for token in self._paragraph_contains)

    def _wants_after_blank(self, low: str) -> bool:
        low = "" if low is None else str(low).casefold()
        if any(low.startswith(str(p).casefold()) for p in self._after_blank_prefixes):
            return True
        return any(str(token).casefold() in low for token in self._after_blank_contains)

    def _enqueue(self, s):
        lines = str(s).splitlines() if s is not None else [""]
        if not lines:
            lines = [""]

        for line in lines:
            raw = self._format_line(str(line))
            is_blank = raw.strip() == ""

            if is_blank:
                if self._last_blank:
                    continue
                self._queue.append("")
                self._last_blank = True
                continue

            low = raw.lstrip().casefold()

            if self._wants_before_blank(low) and not self._last_blank:
                self._queue.append("")
                self._last_blank = True

            self._queue.append(raw)
            self._last_blank = False

            if self._wants_after_blank(low):
                self._queue.append("")
                self._last_blank = True

    def _schedule(self):
        if self._scheduled:
            return
        self._scheduled = True
        try:
            self.widget.after(self.flush_ms, self.flush)
        except Exception:
            self._scheduled = False
            self.flush()

    def flush(self):
        if not self._queue:
            self._scheduled = False
            return
        try:
            self.widget.configure(state="normal")
            self.widget.insert("end", "\n".join(self._queue) + "\n")
            self._queue.clear()

            try:
                total_lines = int(self.widget.index("end-1c").split(".")[0])
                if total_lines > self.max_lines:
                    cut = total_lines - self.max_lines
                    self.widget.delete("1.0", f"{cut+1}.0")
            except Exception:
                pass

            self.widget.configure(state="disabled")
            self.widget.see("end")
            self.widget.update_idletasks()
        except Exception:
            pass
        finally:
            self._scheduled = False
# ------------------------------
# Patch-type selector icons
# ------------------------------
# Loads bps/ips icons without PIL.
# Supports:
#   - ico/bps.png and ico/ips.png (preferred)
#   - ico/bps.ico and ico/ips.ico (PNG frames inside .ico)
def _try_load_png_photoimage(path):
    try:
        import tkinter as tk
        with open(path, "rb") as f:
            b = f.read()
        return tk.PhotoImage(data=base64.b64encode(b))
    except Exception:
        return None


def _extract_best_png_from_ico(ico_path, prefer_size=32):
    # Minimal ICO parser: prefers PNG frames; falls back to None for BMP frames.
    try:
        with open(ico_path, "rb") as f:
            data = f.read()
        if len(data) < 6:
            return None
        reserved, ico_type, count = struct.unpack_from("<HHH", data, 0)
        if reserved != 0 or ico_type != 1 or count <= 0:
            return None
        entries = []
        off = 6
        for _ in range(count):
            if off + 16 > len(data):
                break
            w, h, color_count, _res, planes, bpp, size, offset = struct.unpack_from("<BBBBHHII", data, off)
            off += 16
            w = 256 if w == 0 else w
            h = 256 if h == 0 else h
            entries.append((w, h, size, offset))
        # choose closest to prefer_size, but only PNG payloads
        best = None
        best_score = 10**9
        for w, h, size, offset in entries:
            payload = data[offset:offset+size]
            if payload.startswith(b"\x89PNG\r\n\x1a\n"):
                score = abs(w - prefer_size) + abs(h - prefer_size)
                if score < best_score:
                    best_score = score
                    best = payload
        return best
    except Exception:
        return None


def _try_load_ico_photoimage(path, prefer_size=32):
    try:
        import tkinter as tk
        png = _extract_best_png_from_ico(path, prefer_size=prefer_size)
        if not png:
            return None
        return tk.PhotoImage(data=base64.b64encode(png))
    except Exception:
        return None



def load_patch_type_button_icons(script_dir, prefer_size=32):
    """Return (bps_photoimage, ips_photoimage). Either may be None."""

    candidate_dirs = [
        os.path.join(script_dir, "ico"),
        os.path.join(script_dir, "_internal", "ico"),
    ]

    bps_img = None
    ips_img = None

    for ico_dir in candidate_dirs:
        bps_png = os.path.join(ico_dir, "bps.png")
        ips_png = os.path.join(ico_dir, "ips.png")
        bps_ico = os.path.join(ico_dir, "bps.ico")
        ips_ico = os.path.join(ico_dir, "ips.ico")

        if bps_img is None and os.path.exists(bps_png):
            bps_img = _try_load_png_photoimage(bps_png)
        if ips_img is None and os.path.exists(ips_png):
            ips_img = _try_load_png_photoimage(ips_png)

        if bps_img is None and os.path.exists(bps_ico):
            bps_img = _try_load_ico_photoimage(bps_ico, prefer_size=prefer_size)

        if ips_img is None and os.path.exists(ips_ico):
            ips_img = _try_load_ico_photoimage(ips_ico, prefer_size=prefer_size)

        if bps_img is not None and ips_img is not None:
            break

    return (bps_img, ips_img)


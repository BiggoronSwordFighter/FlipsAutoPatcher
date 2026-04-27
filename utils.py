"""Shared utility helpers for Flips Auto Patcher."""

import os
import binascii
import hashlib
import struct
import base64
import re
from typing import Optional, Callable


# Function to calculate CRC32 of a file
def calculate_crc32(file_path):
    """Stream the file in chunks and return its CRC32 checksum as an unsigned integer.

    This is the fast integrity hash used throughout the patch workflow for ROM and
    patch verification, especially when matching BPS source and target data.
    """
    crc32 = 0
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            crc32 = binascii.crc32(chunk, crc32)
    return crc32 & 0xFFFFFFFF

# Function to calculate MD5 of a file
def calculate_md5(file_path):
    """Read the file in chunks and return its MD5 digest as a lowercase hex string.

    MD5 is shown in the UI as additional verification information for users who want
    to compare files against known hashes from patch notes or ROM databases.
    """
    md5_hash = hashlib.md5()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

# Function to calculate SHA-1 of a file
def calculate_sha1(file_path):
    """Read the file in chunks and return its SHA-1 digest as a lowercase hex string.

    SHA-1 is logged alongside CRC32 and MD5 so the app can display a fuller set of
    hash values for ROM and patch identification.
    """
    sha1_hash = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            sha1_hash.update(chunk)
    return sha1_hash.hexdigest()

# Function to calculate the ZLE hash
def calculate_zle_hash(file_path):
    """Extract the 16-byte N64 ZLE identifier region and return it as trimmed hex text.

    This is mainly useful for N64 workflows where users expect the same short ZLE
    value shown by other ROM tools when comparing variants.
    """
    with open(file_path, 'rb') as f:
        rom_content = f.read()
    zle_value = rom_content[16:28]
    return zle_value.hex().rstrip('0')

# Function to retrieve metadata from a .bps patch file
def get_patch_metadata(patch_file_path):
    """Read a BPS patch and return the hashes and embedded source/target CRC values.

    The returned dictionary feeds the Info/Output area so users can see both the
    patch file hashes and the source/target CRC32 values stored inside the patch.
    """
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


def get_bps_source_size(patch_file_path):
    """Return the embedded BPS source size in bytes, or None on failure."""
    try:
        with open(patch_file_path, 'rb') as f:
            data = f.read()
    except Exception:
        return None

    if not data.startswith(b'BPS1'):
        return None

    i = 4

    def read_bps_number():
        """Decode one variable-length integer from a BPS patch stream.

        BPS stores sizes and command data in a custom varint format, so this helper
        advances the shared byte index and returns the next decoded number.
        """
        nonlocal i
        value = 0
        shift = 1
        while i < len(data):
            x = data[i]
            i += 1
            value += (x & 0x7f) * shift
            if x & 0x80:
                return value
            shift <<= 7
            value += shift
        return None

    try:
        return read_bps_number()
    except Exception:
        return None


# ------------------------------
# IPS helpers (no embedded CRC32)
# ------------------------------
# IPS format: b"PATCH" + records + b"EOF" + optional 3-byte truncate size.
# IPS does NOT store a source/target CRC32. We can only derive structural requirements
# and diagnostics from the file structure itself.

def get_ips_details(patch_file_path):
    """Parse an IPS patch and return structural details.

    The IPS spec uses big-endian 24-bit offsets, 16-bit sizes, and a special RLE
    record form when ``size == 0``. This helper returns enough information for the
    UI to show meaningful IPS metadata and for validation to reject obviously
    incompatible base ROMs before patching.
    """
    details = {
        'valid': False,
        'error': None,
        'min_required_size': 0,
        'truncate_size': None,
        'record_count': 0,
        'rle_record_count': 0,
        'data_record_count': 0,
        'data_bytes': 0,
        'rle_output_bytes': 0,
        'max_offset': 0,
        'has_rle': False,
    }

    try:
        with open(patch_file_path, "rb") as f:
            data = f.read()
    except Exception as e:
        details['error'] = f'read error: {e}'
        return details

    if not data.startswith(b"PATCH"):
        details['error'] = 'missing PATCH header'
        return details

    i = 5
    found_eof = False

    while i + 3 <= len(data):
        if data[i:i+3] == b'EOF':
            i += 3
            found_eof = True
            break

        if i + 5 > len(data):
            details['error'] = 'truncated record header'
            return details

        offset = int.from_bytes(data[i:i+3], 'big')
        i += 3
        size = int.from_bytes(data[i:i+2], 'big')
        i += 2
        details['record_count'] += 1

        if size == 0:
            if i + 3 > len(data):
                details['error'] = 'truncated RLE record'
                return details
            rle_size = int.from_bytes(data[i:i+2], 'big')
            i += 2
            i += 1  # repeated value byte
            details['rle_record_count'] += 1
            details['rle_output_bytes'] += int(rle_size)
            end = offset + rle_size
        else:
            if i + size > len(data):
                details['error'] = 'truncated data record'
                return details
            i += size
            details['data_record_count'] += 1
            details['data_bytes'] += int(size)
            end = offset + size

        if end > details['min_required_size']:
            details['min_required_size'] = int(end)
        if offset > details['max_offset']:
            details['max_offset'] = int(offset)

    if not found_eof:
        details['error'] = 'missing EOF marker'
        return details

    rem = data[i:]
    if len(rem) == 3:
        try:
            details['truncate_size'] = int.from_bytes(rem, 'big')
        except Exception:
            details['truncate_size'] = None
    elif len(rem) != 0:
        details['error'] = f'unexpected trailing data ({len(rem)} bytes)'
        return details

    details['has_rle'] = bool(details['rle_record_count'])
    details['valid'] = True
    return details


def get_ips_requirements(patch_file_path):
    """Return (min_required_size_bytes, truncate_size_bytes_or_None, record_count)."""
    details = get_ips_details(patch_file_path)
    return (
        int(details.get('min_required_size') or 0),
        details.get('truncate_size'),
        int(details.get('record_count') or 0),
    )




# ------------------------------
# ROM header helpers
# ------------------------------

# RomPatcher.js uses a small rule table to decide whether a ROM already has a
# known removable header or can temporarily receive a fake one before patching.
# We mirror that approach here so the desktop app behaves like the website.
_HEADER_RULES = (
    {
        "extensions": {"nes"},
        "size": 16,
        "rom_size_multiple": 1024,
        "name": "iNES",
        "magic": b"NES\x1a",
    },
    {
        "extensions": {"sfc", "smc", "swc", "fig"},
        "size": 512,
        "rom_size_multiple": 262144,
        "name": "SNES copier",
        "magic": None,
    },
)


def _find_header_rule(ext_or_path):
    """Choose the header-handling rule that matches the supplied ROM extension or path.

    The rule table describes removable or temporary headers for specific console
    formats so patching can mirror RomPatcher.js behavior.
    """
    ext = normalize_rom_extension(ext_or_path)
    for rule in _HEADER_RULES:
        if ext in rule["extensions"]:
            return rule
    return None


def _coerce_rom_bytes(data: bytes) -> bytes:
    """Return ROM bytes from either a bytes object or a file path.

    This lets shared ROM helpers accept already-loaded data during processing
    while still supporting direct calls with a filesystem path.
    """
    try:
        return bytes(data)
    except Exception:
        return b""


def get_known_header_info(data: bytes, ext_or_path):
    """Return header info when the ROM appears to contain a known removable header.

    This follows the same style as RomPatcher.js:
      - extension must belong to a known supported type
      - (file_size - header_size) must be a known ROM-size multiple

    For NES we also require the standard iNES magic to avoid stripping the first
    16 bytes from an arbitrary .nes file.
    """
    raw = _coerce_rom_bytes(data)
    rule = _find_header_rule(ext_or_path)
    if not rule:
        return None

    size = len(raw)
    header_size = int(rule["size"])
    rom_size_multiple = int(rule["rom_size_multiple"])

    if size < header_size:
        return None
    if size > (0x600000 + header_size):
        return None
    if (size - header_size) % rom_size_multiple != 0:
        return None

    magic = rule.get("magic")
    if magic and raw[:len(magic)] != magic:
        return None

    return {"name": rule["name"], "size": header_size}


def get_fake_header_info(data: bytes, ext_or_path):
    """Return header info when a ROM can temporarily receive a fake header."""
    raw = _coerce_rom_bytes(data)
    rule = _find_header_rule(ext_or_path)
    if not rule:
        return None

    size = len(raw)
    if size > 0x600000:
        return None
    if size % int(rule["rom_size_multiple"]) != 0:
        return None

    return {"name": rule["name"], "size": int(rule["size"])}



def has_ines_header(data: bytes, ext_or_path='nes') -> bool:
    """Return True when the ROM appears to contain a removable iNES header."""
    info = get_known_header_info(data, ext_or_path)
    return bool(info and info.get("name") == "iNES")


def remove_ines_header_bytes(data: bytes, ext_or_path='nes') -> bytes:
    """Remove a leading 16-byte iNES header when it matches the known-header rule."""
    raw = bytes(data)
    if has_ines_header(raw, ext_or_path=ext_or_path):
        return raw[16:]
    return raw


def add_ines_header_bytes(data: bytes, header_bytes=None, ext_or_path='nes') -> bytes:
    """Prepend a 16-byte iNES header when valid header bytes are available."""
    raw = bytes(data)
    if has_ines_header(raw, ext_or_path=ext_or_path):
        return raw
    header = bytes(header_bytes or b'')
    if len(header) == 16 and header[:4] == b'NES\x1a':
        return header + raw
    return raw


def has_snes_copier_header(data: bytes, ext_or_path='sfc') -> bool:
    """Return True when the ROM appears to contain a removable SNES copier header."""
    info = get_known_header_info(data, ext_or_path)
    return bool(info and info.get("name") == "SNES copier")


def can_add_snes_copier_header(data: bytes, ext_or_path='sfc') -> bool:
    """Return True when a headerless SNES ROM can temporarily receive a fake copier header."""
    info = get_fake_header_info(data, ext_or_path)
    return bool(info and info.get("name") == "SNES copier" and not has_snes_copier_header(data, ext_or_path))


def add_snes_copier_header_bytes(data: bytes, ext_or_path='sfc') -> bytes:
    """Prepend a 512-byte zeroed SNES copier header when the ROM is eligible."""
    raw = bytes(data)
    if has_snes_copier_header(raw, ext_or_path=ext_or_path):
        return raw
    if not can_add_snes_copier_header(raw, ext_or_path=ext_or_path):
        return raw
    return (b"\x00" * 512) + raw


def remove_snes_copier_header_bytes(data: bytes, ext_or_path='sfc') -> bytes:
    """Remove a leading 512-byte SNES copier header when present."""
    raw = bytes(data)
    if has_snes_copier_header(raw, ext_or_path=ext_or_path):
        return raw[512:]
    return raw


def transform_rom_bytes(
    data: bytes,
    *,
    ext_or_path=None,
    remove_ines=False,
    add_ines_header=None,
    add_snes_copier_header=False,
    remove_snes_copier_header=False,
) -> bytes:
    """Apply selected ROM header transforms and return updated bytes."""
    raw = bytes(data)
    if remove_ines:
        raw = remove_ines_header_bytes(raw, ext_or_path=ext_or_path or 'nes')
    if add_ines_header is not None:
        raw = add_ines_header_bytes(raw, header_bytes=add_ines_header, ext_or_path=ext_or_path or 'nes')
    if remove_snes_copier_header:
        raw = remove_snes_copier_header_bytes(raw, ext_or_path=ext_or_path or 'sfc')
    if add_snes_copier_header:
        raw = add_snes_copier_header_bytes(raw, ext_or_path=ext_or_path or 'sfc')
    return raw


def rewrite_rom_file_with_header_options(
    file_path,
    *,
    remove_ines=False,
    add_ines_header=None,
    add_snes_copier_header=False,
    remove_snes_copier_header=False,
):
    """Rewrite an existing ROM file in place and return True when bytes changed."""
    with open(file_path, 'rb') as f:
        original = f.read()
    updated = transform_rom_bytes(
        original,
        ext_or_path=file_path,
        remove_ines=remove_ines,
        add_ines_header=add_ines_header,
        add_snes_copier_header=add_snes_copier_header,
        remove_snes_copier_header=remove_snes_copier_header,
    )
    if updated == original:
        return False
    with open(file_path, 'wb') as f:
        f.write(updated)
    return True

# ------------------------------
# ROM extension helpers
# ------------------------------

def normalize_rom_extension(ext_or_path):
    """Normalize a ROM filename or extension into the lowercase extension token the app uses.

    This keeps extension-based lookups consistent whether the caller passes a full
    path like ``game.sfc`` or just an extension like ``.sfc``.
    """
    try:
        ext = os.path.splitext(str(ext_or_path))[1] if os.path.sep in str(ext_or_path) or str(ext_or_path).endswith(tuple('.'+x for x in ['nes','fds','unf','unif','sfc','smc','fig','gba','agb','gb','gbc','cgb','z64','n64','v64'])) else str(ext_or_path)
    except Exception:
        ext = str(ext_or_path)
    ext = str(ext or '').strip().lower()
    if ext.startswith('.'):
        ext = ext[1:]
    return ext




# ------------------------------
# BPS family / console display helpers
# ------------------------------

def get_rom_family_display(rom_path):
    """Return a short console label for a ROM path for BPS family display.

    This is intentionally conservative and is only used for showing the console
    family for BPS patches after a base ROM has already been matched.
    """
    ext = normalize_rom_extension(rom_path)
    ext_map = {
        'nes': 'nes',
        'fds': 'nes',
        'unf': 'nes',
        'unif': 'nes',
        'sfc': 'snes',
        'smc': 'snes',
        'swc': 'snes',
        'fig': 'snes',
        'gba': 'gba',
        'agb': 'gba',
        'gb': 'gb',
        'gbc': 'gbc',
        'cgb': 'gbc',
        'sms': 'sms',
        'pce': 'pce',
        'gen': 'genesis',
        'md': 'genesis',
        'bin': 'genesis',
        'rom': 'rom',
        'z64': 'n64',
        'n64': 'n64',
        'v64': 'n64',
    }
    family = ext_map.get(ext, '')
    if family != 'gb':
        return family

    # Distinguish GB vs GBC from the cartridge header when the file extension is .gb.
    try:
        with open(rom_path, 'rb') as f:
            data = f.read(0x150)
        if len(data) > 0x143 and data[0x143] in (0x80, 0xC0):
            return 'gbc'
    except Exception:
        pass
    return family

def validate_ips_base_rom(patch_file_path, base_rom_path):
    """Return (ok, reason, details) for an IPS/base-ROM pairing.

    IPS has no embedded source checksum, so validation here is intentionally
    structural only:
      1) require the ROM to be at least as large as the highest byte touched by
         the IPS records
      2) when the patch carries a 3-byte truncate size, require the ROM size to
         match that expected size exactly
      3) reject malformed IPS files before any patch attempt starts
    """
    details = get_ips_details(patch_file_path)
    try:
        rom_size = int(os.path.getsize(base_rom_path))
    except Exception:
        rom_size = 0

    details.update({'rom_size': rom_size})
    min_size = int(details.get('min_required_size') or 0)
    trunc_size = details.get('truncate_size')

    if not details.get('valid'):
        return False, f"invalid IPS patch ({details.get('error') or 'parse error'})", details

    if min_size and rom_size < min_size:
        return False, f'base ROM too small ({rom_size} < required {min_size})', details

    if trunc_size is not None and trunc_size > 0 and rom_size != trunc_size:
        return False, f'truncate/file-size mismatch ({rom_size} != {trunc_size})', details

    return True, 'ok', details

def get_ips_metadata(patch_file_path):
    """Return a metadata dict for IPS patches (hashes + IPS-only structural fields)."""
    try:
        crc32 = calculate_crc32(patch_file_path)
        md5 = calculate_md5(patch_file_path)
        sha1 = calculate_sha1(patch_file_path)
        zle = calculate_zle_hash(patch_file_path)
        details = get_ips_details(patch_file_path)

        meta = {
            "CRC32": f"{crc32:#010x}",
            "MD5": md5,
            "SHA-1": sha1,
            "ZLE": zle,
            "Min Required Size": str(int(details.get('min_required_size') or 0)),
            "Record Count": str(int(details.get('record_count') or 0)),
            "RLE Records": str(int(details.get('rle_record_count') or 0)),
            "Data Records": str(int(details.get('data_record_count') or 0)),
            "Max Offset": str(int(details.get('max_offset') or 0)),
        }
        if details.get('truncate_size') is not None:
            meta["Truncate Size"] = str(int(details['truncate_size']))
        if details.get('has_rle'):
            meta["RLE Output Bytes"] = str(int(details.get('rle_output_bytes') or 0))
        if details.get('error'):
            meta["IPS Warning"] = str(details['error'])
        return meta
    except Exception as e:
        print(f"Error reading IPS patch file {patch_file_path}: {e}")
        return None


LOG_LABEL_WIDTH = 32


def format_log_field(label: str, value: str = "") -> str:
    """Format a ``Label: value`` pair so log output lines up cleanly in the Info/Output box.

    Centralizing the padding here keeps hash lines, file locations, and other status
    details visually consistent across the app.
    """
    return f"  {str(label):<{LOG_LABEL_WIDTH}}: {value}"


def log_operation_paths(log_fn: Optional[Callable[[str], None]], *, patch_file_path=None, base_rom_path=None, modified_rom_path=None, output_file_path=None, header: str | None = None) -> None:
    """Log a consistent path block for patch/apply/create operations."""
    if not callable(log_fn):
        return

    lines = []
    if patch_file_path:
        lines.append(format_log_field("Patch File Location", os.path.abspath(str(patch_file_path))))
    if base_rom_path:
        lines.append(format_log_field("Base ROM location", os.path.abspath(str(base_rom_path))))
    if modified_rom_path:
        lines.append(format_log_field("Modified ROM location", os.path.abspath(str(modified_rom_path))))
    if output_file_path:
        lines.append(format_log_field("Output file location", os.path.abspath(str(output_file_path))))

    for line in lines:
        try:
            log_fn(line)
        except Exception:
            pass



def log_patch_requirements(log_fn: Optional[Callable[[str], None]], patch_file_path, rom_path=None) -> None:
    """Compatibility shim kept for older call sites."""
    return


# ------------------------------
# GUI logging helpers (Tkinter)
# ------------------------------
# Centralized, buffered writer for the Info/Output box.
# - Prevents double-blank-line spam
# - Batches inserts to reduce redraw overhead in bulk operations


class GUILogger:
    """Buffered writer for the Info/Output box."""

    def __init__(self, widget, *, max_lines=6000, flush_ms=25):
        """Set up the buffered GUI logger and define the line patterns that create spacing.

        The logger queues text, normalizes repeated status formats, and inserts blank
        lines around important sections so the ScrolledText widget stays readable.
        """
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

            # Rom header options
            "ROM Header Options → NES:",
 
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
            "Patching process is complete.",
            "patch creation process has started.",
            "patch creation process is complete.",
            "Successfully applied patch",
            "rom header options:",
            "note:",

            # Open-with flow (open_with_handle.py) 
            "no modified rom file selected.",
            "no valid rom or patch file selected.",

            # Bulk mode (bulk.py)
            "bulk patching enabled",
            "bulk patching:",
            "bulk patching -",
            "bulk patching folder was not found.",
            "Skipped emulator launch for",
            "created folder:",

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

            # Rom header options
            "ROM Header Options → SNES:",

            # Hash/metadata blocks: add a space after the block ends.
            "select the base rom file.",
            "No Base ROM file selected.",

            # Bulk mode (bulk.py)
            "bulk patching -",
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
        """Queue one message for display and optionally add a section heading first.

        Messages are buffered instead of written immediately so bursts of logging do
        not make the Tk text widget flicker or update excessively.
        """
        msg = "" if message is None else str(message)

        if section:
            self._enqueue("")
            self._enqueue(f"=== {section} ===")

        self._enqueue(msg)
        self._schedule()

    def _format_line(self, raw: str) -> str:
        """Normalize well-known status lines into the aligned display format used by the UI.

        This mainly rewrites hash and metadata lines so they appear with consistent
        labels regardless of how the calling code originally formatted them.
        """
        raw = raw.rstrip("\n")

        m = re.match(r"^\s*(CRC32|MD5|SHA-1|ZLE|Source CRC32|Target CRC32|Min Required Size|Record Count|Truncate Size|RLE Records|Data Records|Max Offset|RLE Output Bytes|IPS Warning|Endian|Patch File Location|Base ROM location|Modified ROM location|Output file location|Applied using)\s*:\s*(.*)$", raw, re.IGNORECASE)
        if m:
            key, val = m.group(1), m.group(2)
            if str(key).casefold() == "applied using":
                return ""
            canonical = {
                "crc32": "CRC32",
                "md5": "MD5",
                "sha-1": "SHA-1",
                "zle": "ZLE",
                "source crc32": "Source CRC32",
                "target crc32": "Target CRC32",
                "min required size": "Min Required Size",
                "record count": "Record Count",
                "truncate size": "Truncate Size",
                "rle records": "RLE Records",
                "data records": "Data Records",
                "max offset": "Max Offset",
                "rle output bytes": "RLE Output Bytes",
                "ips warning": "IPS Warning",
                "endian": "Endian",
                "patch file location": "Patch File Location",
                "base rom location": "Base ROM location",
                "modified rom location": "Modified ROM location",
                "output file location": "Output file location",
            }.get(str(key).strip().casefold(), str(key).strip())
            return format_log_field(canonical, val)

        m2 = re.match(r"^\s*(IPS requirements|BPS requirements):\s*(.*)$", raw, re.IGNORECASE)
        if m2:
            return format_log_field(m2.group(1), m2.group(2))

        return raw

    def _wants_before_blank(self, low: str) -> bool:
        """Return True when a line should be preceded by a blank separator in the log.

        This is used to visually break up major workflow milestones such as selected
        files, patch results, cleanup tasks, and other user-facing status updates.
        """
        low = "" if low is None else str(low).casefold()
        if any(low.startswith(str(p).casefold()) for p in self._paragraph_prefixes):
            return True
        return any(str(token).casefold() in low for token in self._paragraph_contains)

    def _wants_after_blank(self, low: str) -> bool:
        """Return True when a line should be followed by a blank separator in the log.

        The after-blank rules are intentionally conservative so spacing stays neat
        without scattering empty lines everywhere.
        """
        low = "" if low is None else str(low).casefold()
        if any(low.startswith(str(p).casefold()) for p in self._after_blank_prefixes):
            return True
        return any(str(token).casefold() in low for token in self._after_blank_contains)

    def _enqueue(self, s):
        """Split incoming text into lines, collapse duplicate blank lines, and queue the result.

        This is the central place where log formatting rules are applied before any
        text is actually inserted into the widget.
        """
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
        """Request a deferred flush on the Tk event loop if one is not already pending.

        Scheduling a batched flush keeps GUI updates responsive while avoiding one
        widget write per individual log message.
        """
        if self._scheduled:
            return
        self._scheduled = True
        try:
            self.widget.after(self.flush_ms, self.flush)
        except Exception:
            self._scheduled = False
            self.flush()

    def flush(self):
        """Write the queued log lines into the text widget, trim old history, and scroll to the end.

        This is the only method that touches the widget directly, which helps keep
        the logger thread-safe enough for normal Tkinter usage patterns.
        """
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
    """Load a PNG file into a Tk ``PhotoImage`` without depending on Pillow.

    The button-icon loader prefers plain PNG assets because Tk can display them
    directly after the bytes are base64-encoded.
    """
    try:
        import tkinter as tk
        with open(path, "rb") as f:
            b = f.read()
        return tk.PhotoImage(data=base64.b64encode(b))
    except Exception:
        return None


def _extract_best_png_from_ico(ico_path, prefer_size=32):
    # Minimal ICO parser: prefers PNG frames; falls back to None for BMP frames.
    """Parse an ICO file and return the PNG frame whose size is closest to ``prefer_size``.

    Many ICO files contain multiple images; this helper picks the most suitable PNG
    payload so Tk can reuse it as a normal ``PhotoImage``.
    """
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
    """Load an ICO file by extracting a PNG frame and converting it into a Tk ``PhotoImage``.

    This gives the UI a no-Pillow fallback when only ``.ico`` assets are available
    for the BPS and IPS selector buttons.
    """
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


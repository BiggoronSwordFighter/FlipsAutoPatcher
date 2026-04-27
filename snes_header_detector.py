#!/usr/bin/env python3
"""
snes_header_detector.py

Detect:
1) whether a ROM currently has a 512-byte SNES copier header
2) the likely SNES internal header/layout
3) whether the copier header looks like a simple generated header or a richer/custom one

Important:
- Detecting a PRESENT SNES copier header is heuristic.
- Determining whether it is the "original" header is also heuristic.
"""

from __future__ import annotations

import argparse
import os
import struct
from dataclasses import dataclass
from typing import Optional


@dataclass
class HeaderCandidate:
    name: str
    file_offset: int
    score: int
    title: str
    map_mode: int
    rom_type: int
    rom_size: int
    ram_size: int
    region: int
    developer_id: int
    version: int
    checksum_complement: int
    checksum: int
    reset_vector: int


MAP_MODE_NAMES = {
    0x20: "LoROM",
    0x21: "HiROM",
    0x22: "LoROM + S-DD1",
    0x23: "LoROM + SA-1",
    0x25: "ExHiROM",
    0x30: "Fast LoROM",
    0x31: "Fast HiROM",
    0x32: "Fast LoROM + S-DD1",
    0x35: "Fast ExHiROM",
}


REGION_NAMES = {
    0x00: "Japan",
    0x01: "North America",
    0x02: "Europe",
    0x03: "Sweden/Scandinavia",
    0x04: "Finland",
    0x05: "Denmark",
    0x06: "France",
    0x07: "Netherlands",
    0x08: "Spain",
    0x09: "Germany/Austria/Switzerland",
    0x0A: "Italy",
    0x0B: "Hong Kong/China",
    0x0C: "Indonesia",
    0x0D: "South Korea",
}


def read_u8(data: bytes, offset: int) -> int:
    return data[offset]


def read_u16_le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def is_probably_ascii_title(raw: bytes) -> bool:
    for b in raw:
        if b == 0x00:
            continue
        if 0x20 <= b <= 0x7E:
            continue
        return False
    return True


def clean_title(raw: bytes) -> str:
    return raw.decode("ascii", errors="replace").rstrip("\x00 ").strip()


def detect_copier_header(data: bytes) -> int:
    return 512 if len(data) % 1024 == 512 else 0


def classify_copier_header_provenance(data: bytes, copier_header_size: int) -> tuple[str, str]:
    if not copier_header_size:
        return "unknown", "No SNES copier header detected."

    header = data[:copier_header_size]
    zero_count = header.count(0)
    ff_count = header.count(0xFF)
    non_zero = copier_header_size - zero_count

    if zero_count == copier_header_size:
        return "likely regenerated/minimal", "The 512-byte copier header is entirely zero-filled, which strongly suggests a generated placeholder header."

    if ff_count == copier_header_size:
        return "likely regenerated/minimal", "The 512-byte copier header is entirely 0xFF-filled, which strongly suggests a generated placeholder header."

    if non_zero <= 16:
        return "likely regenerated/minimal", "The 512-byte copier header is almost entirely empty, with very little non-zero metadata."

    return "possibly original/customized", "The 512-byte copier header contains substantial non-zero metadata, so it may be an original/custom copier header."


def score_header(data: bytes, offset: int, expected_kind: str) -> Optional[HeaderCandidate]:
    if offset < 0 or offset + 0x20 > len(data):
        return None

    title_raw = data[offset : offset + 21]
    map_mode = read_u8(data, offset + 0x15)
    rom_type = read_u8(data, offset + 0x16)
    rom_size = read_u8(data, offset + 0x17)
    ram_size = read_u8(data, offset + 0x18)
    region = read_u8(data, offset + 0x19)
    developer_id = read_u8(data, offset + 0x1A)
    version = read_u8(data, offset + 0x1B)
    checksum_complement = read_u16_le(data, offset + 0x1C)
    checksum = read_u16_le(data, offset + 0x1E)

    reset_vector_offset = offset + 0x1C
    if reset_vector_offset + 2 > len(data):
        return None
    reset_vector = read_u16_le(data, reset_vector_offset)

    score = 0

    if is_probably_ascii_title(title_raw):
        score += 8
    title = clean_title(title_raw)
    if title:
        score += 4

    if (checksum ^ checksum_complement) == 0xFFFF:
        score += 8

    if map_mode in MAP_MODE_NAMES:
        score += 6

    if region <= 0x14:
        score += 2

    if version <= 0x20:
        score += 1

    if 0x08 <= rom_size <= 0x1A:
        score += 2
    if ram_size <= 0x0D:
        score += 1

    if 0x8000 <= reset_vector <= 0xFFEF:
        score += 8
    elif reset_vector not in (0x0000, 0xFFFF):
        score += 2

    if expected_kind == "LoROM" and map_mode in (0x20, 0x30, 0x22, 0x23):
        score += 3
    if expected_kind == "HiROM" and map_mode in (0x21, 0x31, 0x25, 0x35):
        score += 3
    if expected_kind == "ExHiROM" and map_mode in (0x25, 0x35):
        score += 3

    return HeaderCandidate(
        name=expected_kind,
        file_offset=offset,
        score=score,
        title=title,
        map_mode=map_mode,
        rom_type=rom_type,
        rom_size=rom_size,
        ram_size=ram_size,
        region=region,
        developer_id=developer_id,
        version=version,
        checksum_complement=checksum_complement,
        checksum=checksum,
        reset_vector=reset_vector,
    )


def find_best_header(data: bytes, copier_header_size: int) -> Optional[HeaderCandidate]:
    candidates: list[HeaderCandidate] = []

    common_locations = [
        ("LoROM", copier_header_size + 0x7FC0),
        ("HiROM", copier_header_size + 0xFFC0),
        ("ExHiROM", copier_header_size + 0x40FFC0),
    ]

    for name, offset in common_locations:
        cand = score_header(data, offset, name)
        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[0]


def format_size_from_exponent(exp: int) -> str:
    size_bytes = 1024 << exp
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes // (1024 * 1024)} MiB"
    if size_bytes >= 1024:
        return f"{size_bytes // 1024} KiB"
    return f"{size_bytes} B"


def print_header_info(path: str, data: bytes, copier_header_size: int, header: HeaderCandidate) -> None:
    provenance, provenance_reason = classify_copier_header_provenance(data, copier_header_size)

    print(f"File:              {path}")
    print(f"File size:         {len(data)} bytes")
    print(f"Copier header:     {'Yes (512 bytes)' if copier_header_size else 'No'}")
    print(f"Header provenance: {provenance}")
    print(f"Detected layout:   {header.name}")
    print(f"Header file offset: 0x{header.file_offset:06X}")
    print(f"Heuristic score:   {header.score}")
    print()
    print(f"Title:             {header.title or '(blank)'}")
    print(
        f"Map mode:          0x{header.map_mode:02X}"
        f" ({MAP_MODE_NAMES.get(header.map_mode, 'Unknown')})"
    )
    print(f"ROM type:          0x{header.rom_type:02X}")
    print(
        f"ROM size code:     0x{header.rom_size:02X}"
        f" ({format_size_from_exponent(header.rom_size)})"
    )
    print(
        f"RAM size code:     0x{header.ram_size:02X}"
        f" ({format_size_from_exponent(header.ram_size)})"
    )
    print(
        f"Region:            0x{header.region:02X}"
        f" ({REGION_NAMES.get(header.region, 'Unknown')})"
    )
    print(f"Developer ID:      0x{header.developer_id:02X}")
    print(f"Version:           0x{header.version:02X}")
    print(f"Checksum comp:     0x{header.checksum_complement:04X}")
    print(f"Checksum:          0x{header.checksum:04X}")
    print(
        f"Checksum valid:    "
        f"{'Yes' if (header.checksum ^ header.checksum_complement) == 0xFFFF else 'No'}"
    )
    print(f"Reset vector:      0x{header.reset_vector:04X}")
    print(f"Provenance reason: {provenance_reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read SNES internal ROM header and detect copier header provenance.")
    parser.add_argument("rom", help="Path to SNES ROM file (.smc, .sfc, etc.)")
    args = parser.parse_args()

    if not os.path.isfile(args.rom):
        print(f"Error: file not found: {args.rom}")
        return 1

    with open(args.rom, "rb") as f:
        data = f.read()

    copier_header_size = detect_copier_header(data)
    best = find_best_header(data, copier_header_size)

    if best is None:
        print("Could not find a plausible SNES header.")
        return 2

    print_header_info(args.rom, data, copier_header_size, best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

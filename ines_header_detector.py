#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ines_header_detector.py

Detect:
1) whether a ROM currently has an iNES/NES 2.0 header
2) whether a ROM may have had its 16-byte iNES header removed
3) whether the present header looks like a minimal/generated header or a richer/original-looking one

Important:
- Detecting a PRESENT iNES header is reliable.
- Detecting that a header was REMOVED is heuristic.
- Determining whether a header is the "original" one is also heuristic.
"""

from __future__ import annotations

import argparse
import os
import struct
from dataclasses import dataclass

INES_MAGIC = b"NES\x1a"
INES_HEADER_SIZE = 16


@dataclass
class DetectionResult:
    path: str
    file_size: int
    has_ines_header: bool
    is_nes2: bool
    likely_header_removed: bool
    confidence: str
    reason: str
    header_kind: str
    header_provenance: str
    header_provenance_reason: str


def read_file_prefix(path: str, size: int = 64) -> bytes:
    with open(path, "rb") as f:
        return f.read(size)


def has_ines_header_bytes(data: bytes) -> bool:
    return len(data) >= INES_HEADER_SIZE and data[:4] == INES_MAGIC


def is_nes2_header(header: bytes) -> bool:
    if not has_ines_header_bytes(header):
        return False
    flags7 = header[7]
    return (flags7 & 0x0C) == 0x08


def parse_ines_sizes(header: bytes) -> tuple[int, int]:
    prg_units = header[4]
    chr_units = header[5]
    prg_size = prg_units * 16 * 1024
    chr_size = chr_units * 8 * 1024
    return prg_size, chr_size


def vector_score(raw_rom: bytes) -> int:
    if len(raw_rom) < 6:
        return 0
    tail = raw_rom[-6:]
    try:
        nmi, reset, irq = struct.unpack("<HHH", tail)
    except struct.error:
        return 0

    score = 0
    for value in (nmi, reset, irq):
        if 0x8000 <= value <= 0xFFFF:
            score += 1
    return score


def classify_ines_header_provenance(header: bytes, file_size: int) -> tuple[str, str]:
    if not has_ines_header_bytes(header):
        return "unknown", "No iNES header present."

    prg_size, chr_size = parse_ines_sizes(header)
    trainer = bool(header[6] & 0x04)
    trainer_size = 512 if trainer else 0
    expected_min = INES_HEADER_SIZE + trainer_size + prg_size + chr_size

    flags6 = header[6]
    flags7 = header[7]
    tail = header[8:16]

    nonzero_tail = sum(1 for b in tail if b != 0)
    simple_mapper = ((flags6 >> 4) | (flags7 & 0xF0)) == 0
    simple_flags = (flags6 & 0x0F) in (0, 1) and flags7 in (0, 8)

    if nonzero_tail == 0 and simple_mapper and simple_flags:
        if expected_min == file_size:
            return (
                "likely regenerated/minimal",
                "Header uses the standard iNES magic and a very minimal field pattern; trailing header bytes are zero and file size matches the simple PRG/CHR expectation exactly.",
            )
        return (
            "likely regenerated/minimal",
            "Header uses a very minimal field pattern with mostly zero/default bytes.",
        )

    if nonzero_tail >= 2 or not simple_mapper or not simple_flags:
        return (
            "possibly original/customized",
            "Header contains non-trivial mapper/flag bytes or non-zero extended fields, so it does not look like a bare minimum generated header.",
        )

    return "unknown", "Header is present, but its provenance cannot be determined confidently."


def likely_header_removed_bytes(data: bytes, path: str) -> tuple[bool, str, str]:
    if has_ines_header_bytes(data):
        return False, "high", "Valid iNES/NES 2.0 header is present."

    file_size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()

    score = 0
    reasons = []

    if ext == ".nes":
        score += 2
        reasons.append("File uses .nes extension but does not start with iNES magic.")

    if file_size % (16 * 1024) == 0:
        score += 2
        reasons.append("File size is an exact multiple of 16 KiB, which matches raw PRG-ROM alignment.")
    elif file_size % (8 * 1024) == 0:
        score += 1
        reasons.append("File size is an exact multiple of 8 KiB, which can match raw CHR/PRG alignment.")

    with open(path, "rb") as f:
        raw = f.read()

    vscore = vector_score(raw)
    if vscore >= 2:
        score += 2
        reasons.append("The last bytes contain plausible NES interrupt/reset vectors.")
    elif vscore == 1:
        score += 1
        reasons.append("The last bytes contain one plausible NES vector.")

    if file_size < 16 * 1024:
        reasons.append("File is smaller than a typical NES PRG image.")
        return False, "low", " ; ".join(reasons) if reasons else "Too small to classify confidently."

    if score >= 5:
        return True, "medium", " ; ".join(reasons)
    if score >= 3:
        return True, "low", " ; ".join(reasons)

    return False, "low", " ; ".join(reasons) if reasons else "No strong signs of header removal."


def detect_ines_header(path: str) -> DetectionResult:
    prefix = read_file_prefix(path, 64)
    file_size = os.path.getsize(path)

    if has_ines_header_bytes(prefix):
        header = prefix[:16]
        nes2 = is_nes2_header(header)
        prg_size, chr_size = parse_ines_sizes(header)
        trainer = bool(header[6] & 0x04)
        trainer_size = 512 if trainer else 0
        expected_min = INES_HEADER_SIZE + trainer_size + prg_size + chr_size

        reason = (
            f"Valid {'NES 2.0' if nes2 else 'iNES'} header detected. "
            f"PRG={prg_size} bytes, CHR={chr_size} bytes, "
            f"{'trainer present' if trainer else 'no trainer'}."
        )
        if not nes2 and expected_min != file_size:
            reason += f" File size ({file_size}) does not exactly match classic iNES payload expectation ({expected_min})."

        provenance, provenance_reason = classify_ines_header_provenance(header, file_size)

        return DetectionResult(
            path=path,
            file_size=file_size,
            has_ines_header=True,
            is_nes2=nes2,
            likely_header_removed=False,
            confidence="high",
            reason=reason,
            header_kind="NES 2.0" if nes2 else "iNES",
            header_provenance=provenance,
            header_provenance_reason=provenance_reason,
        )

    likely_removed, confidence, reason = likely_header_removed_bytes(prefix, path)
    return DetectionResult(
        path=path,
        file_size=file_size,
        has_ines_header=False,
        is_nes2=False,
        likely_header_removed=likely_removed,
        confidence=confidence,
        reason=reason,
        header_kind="none detected",
        header_provenance="unknown",
        header_provenance_reason="No iNES header is present, so provenance cannot be determined.",
    )


def print_report(result: DetectionResult) -> None:
    print(f"File:                 {result.path}")
    print(f"File size:            {result.file_size} bytes")
    print(f"iNES header present:  {'Yes' if result.has_ines_header else 'No'}")
    print(f"Header kind:          {result.header_kind}")
    print(f"NES 2.0 header:       {'Yes' if result.is_nes2 else 'No'}")
    print(f"Likely header removed:{' Yes' if result.likely_header_removed else ' No'}")
    print(f"Header provenance:    {result.header_provenance}")
    print(f"Confidence:           {result.confidence}")
    print(f"Reason:               {result.reason}")
    print(f"Provenance reason:    {result.header_provenance_reason}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect whether a ROM has an iNES header, may have had it removed, and whether the header looks original/minimal."
    )
    parser.add_argument("rom", help="Path to ROM file")
    args = parser.parse_args()

    try:
        result = detect_ines_header(args.rom)
        print_report(result)
        return 0
    except FileNotFoundError:
        print(f"Error: file not found: {args.rom}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

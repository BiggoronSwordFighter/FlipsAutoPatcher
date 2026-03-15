import os
import sys

FILE_EXTENSIONS = {
    ".nes", ".sfc", ".smc", ".gba", ".gbc",
    ".gen", ".md", ".bin", ".rom",
    ".z64", ".n64", ".v64",
    ".sms", ".pce"
}

MAGIC_TO_FORMAT = {
    b"\x80\x37\x12\x40": "z64",
    b"\x40\x12\x37\x80": "n64",
    b"\x37\x80\x40\x12": "v64",
}


def swap16(data: bytes) -> bytes:
    return b"".join(data[i:i+2][::-1] for i in range(0, len(data), 2))


def swap32(data: bytes) -> bytes:
    out = bytearray(data)
    for i in range(0, len(out), 4):
        out[i:i+4] = out[i:i+4][::-1]
    return bytes(out)


# Conversion helpers
TO_Z64 = {
    "z64": lambda d: d,
    "v64": swap16,
    "n64": swap32,
}

FROM_Z64 = {
    "z64": lambda d: d,
    "v64": swap16,
    "n64": swap32,
}


def detect_format(data: bytes) -> str:
    try:
        return MAGIC_TO_FORMAT[data[:4]]
    except KeyError:
        raise ValueError("Unknown N64 ROM format (invalid magic)")


def convert(data: bytes, src: str, dst: str) -> bytes:
    if src == dst:
        return data
    return FROM_Z64[dst](TO_Z64[src](data))


def process_file(path: str):
    ext = os.path.splitext(path)[1].lower()

    if ext not in FILE_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    if ext not in {".z64", ".n64", ".v64"}:
        print("File does not use endian swapping.")
        return

    with open(path, "rb") as f:
        data = f.read()

    src = detect_format(data)
    print(f"Detected source format: {src.upper()}")

    print("\nChoose output format:")
    for i, fmt in enumerate(("z64", "n64", "v64"), 1):
        print(f"{i} = {fmt.upper()}")

    choice = input("Selection: ").strip()
    options = {"1": "z64", "2": "n64", "3": "v64"}

    if choice not in options:
        print("Invalid selection.")
        return

    dst = options[choice]
    out_data = convert(data, src, dst)

    out_path = f"{os.path.splitext(path)[0]}.{dst}"
    with open(out_path, "wb") as f:
        f.write(out_data)

    print(f"\nOutput written to: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python endian_swap.py <rom_file>")
        sys.exit(1)

    process_file(sys.argv[1])
import os
import binascii
import hashlib
import struct

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
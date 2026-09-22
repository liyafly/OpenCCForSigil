from __future__ import annotations

import struct

import pytest

from tools.build_opencc_jieba import _cmake_baseline_options
from tools.native_compatibility import NativeCompatibilityError, validate_binary_bytes


def _macho(*, architecture: str = "arm64", minos: tuple[int, int, int] = (13, 0, 0)) -> bytes:
    cputype = {"arm64": 0x0100000C, "x86_64": 0x01000007}[architecture]
    encoded_minos = (minos[0] << 16) | (minos[1] << 8) | minos[2]
    command = struct.pack("<IIIIII", 0x32, 24, 1, encoded_minos, encoded_minos, 0)
    header = struct.pack("<IIIIIIII", 0xFEEDFACF, cputype, 0, 6, 1, len(command), 0, 0)
    return header + command


def _elf64(*, glibc: str = "2.35", glibcxx: str = "3.4.30") -> bytes:
    dynstr = (
        b"\0libc.so.6\0libstdc++.so.6\0GLIBC_"
        + glibc.encode()
        + b"\0GLIBCXX_"
        + glibcxx.encode()
        + b"\0"
    )
    libc_offset = dynstr.index(b"libc.so.6")
    libstdcxx_offset = dynstr.index(b"libstdc++.so.6")
    glibc_offset = dynstr.index(b"GLIBC_")
    glibcxx_offset = dynstr.index(b"GLIBCXX_")
    versym = struct.pack("<HHH", 0, 2, 3)
    verneed = b""
    for index, (library, version_index, version) in enumerate(
        ((libc_offset, 2, glibc_offset), (libstdcxx_offset, 3, glibcxx_offset))
    ):
        verneed += struct.pack("<HHIII", 1, 1, library, 16, 32 if index == 0 else 0)
        verneed += struct.pack("<IHHII", 0, 0, version_index, version, 0)
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0),
        (3, len(dynstr), 1, 0, 0, 0, 0, 1),
        (11, 0, 0, 0, 0, 0, 0, 0),
        (0x6FFFFFFF, len(versym), 2, 0, 0, 0, 0, 2),
        (0x6FFFFFFE, len(verneed), 1, 0, 0, 0, 0, 0),
        (3, 1, 0, 0, 0, 0, 0, 1),
    ]
    body = bytearray(b"\0" * 64)
    section_offsets = [0] * len(sections)
    for index, content in ((1, dynstr), (3, versym), (4, verneed), (5, b"\0.shstrtab\0")):
        section_offsets[index] = len(body)
        body.extend(content)
    shoff = len(body)
    body.extend(b"\0" * (len(sections) * 64))
    for index, (section_type, size, link, _, _, _, _, entry_size) in enumerate(sections):
        offset = section_offsets[index] if index < len(section_offsets) else 0
        if index == 2:
            offset = 0
        sh = (0, section_type, 0, 0, offset, size, link, 0, 1, entry_size)
        struct.pack_into("<IIQQQQIIQQ", body, shoff + index * 64, *sh)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH",
        body,
        0,
        b"\x7fELF" + bytes((2, 1, 1, 0)) + b"\0" * 8,
        3,
        62,
        1,
        0,
        0,
        shoff,
        0,
        64,
        0,
        0,
        64,
        len(sections),
        5,
    )
    return bytes(body)


def _pe64(machine: int = 0x8664) -> bytes:
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, machine)
    return bytes(data)


def test_macos_binary_accepts_arm64_at_supported_baseline():
    validate_binary_bytes(_macho(), runtime_os="macos", architecture="arm64")


def test_macos_binary_rejects_above_deployment_baseline():
    with pytest.raises(NativeCompatibilityError, match=r"minimum 14\.0 exceeds"):
        validate_binary_bytes(_macho(minos=(14, 0, 0)), runtime_os="macos", architecture="arm64")


def test_macos_binary_rejects_wrong_architecture():
    with pytest.raises(NativeCompatibilityError, match="architecture mismatch"):
        validate_binary_bytes(
            _macho(architecture="x86_64"), runtime_os="macos", architecture="arm64"
        )


def test_linux_binary_accepts_ubuntu_2204_version_floor():
    validate_binary_bytes(_elf64(), runtime_os="linux", architecture="x86_64")


@pytest.mark.parametrize(
    ("glibc", "glibcxx", "message"),
    [
        ("2.36", "3.4.30", "GLIBC minimum 2.36 exceeds"),
        ("2.35", "3.4.31", "GLIBCXX minimum 3.4.31 exceeds"),
    ],
)
def test_linux_binary_rejects_versions_above_baseline(glibc, glibcxx, message):
    with pytest.raises(NativeCompatibilityError, match=message):
        validate_binary_bytes(
            _elf64(glibc=glibc, glibcxx=glibcxx), runtime_os="linux", architecture="x86_64"
        )


def test_linux_binary_rejects_missing_version_metadata():
    malformed = bytearray(_elf64())
    # Remove the GNU version requirement table while leaving the section table
    # structurally intact; a missing table must fail closed.
    shoff = struct.unpack_from("<Q", malformed, 40)[0]
    struct.pack_into("<I", malformed, shoff + 4 * 64 + 4, 0)
    with pytest.raises(NativeCompatibilityError, match="version metadata is missing"):
        validate_binary_bytes(bytes(malformed), runtime_os="linux", architecture="x86_64")


def test_linux_binary_rejects_unparseable_version_name():
    with pytest.raises(NativeCompatibilityError, match="unparseable GLIBC version metadata"):
        validate_binary_bytes(
            _elf64(glibc="not-a-version"), runtime_os="linux", architecture="x86_64"
        )


def test_windows_binary_checks_machine_type():
    validate_binary_bytes(_pe64(), runtime_os="windows", architecture="x86_64")
    with pytest.raises(NativeCompatibilityError, match="architecture mismatch"):
        validate_binary_bytes(_pe64(machine=0xAA64), runtime_os="windows", architecture="x86_64")


def test_malformed_binary_fails_closed():
    with pytest.raises(NativeCompatibilityError, match="unrecognized"):
        validate_binary_bytes(b"not a native library", runtime_os="macos", architecture="arm64")


def test_native_build_recipes_pin_supported_host_baselines():
    assert _cmake_baseline_options("macos") == ["-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0"]
    assert _cmake_baseline_options("linux") == [
        "-DCMAKE_C_COMPILER=gcc-11",
        "-DCMAKE_CXX_COMPILER=g++-11",
    ]
    assert _cmake_baseline_options("windows") == []

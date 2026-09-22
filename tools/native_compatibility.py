#!/usr/bin/env python3
"""Check native Jieba binaries against the supported Sigil host baselines.

The checker deliberately uses only the Python standard library.  Build and
release validation may run on a different operating system from the payload
being inspected, and the final ZIP must be checkable without loading any of
its native libraries.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import struct
from pathlib import Path


class NativeCompatibilityError(ValueError):
    """Raised when a native payload is malformed or exceeds a host baseline."""


@dataclass(frozen=True)
class CompatibilityPolicy:
    macos_max: tuple[int, int, int] = (13, 0, 0)
    linux_glibc_max: tuple[int, int, int] = (2, 35, 0)
    linux_glibcxx_max: tuple[int, int, int] = (3, 4, 30)


POLICY = CompatibilityPolicy()

_MACHO_CPU_TYPES = {"x86_64": 0x01000007, "arm64": 0x0100000C}
_ELF_MACHINES = {"x86_64": 62, "arm64": 183}
_PE_MACHINES = {"x86_64": 0x8664, "arm64": 0xAA64}
_GLIBC_RE = re.compile(r"^GLIBC_(\d+)\.(\d+)(?:\.(\d+))?$")
_GLIBCXX_RE = re.compile(r"^GLIBCXX_(\d+)\.(\d+)(?:\.(\d+))?$")


def _version(raw: int) -> tuple[int, int, int]:
    return ((raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF)


def _version_text(value: tuple[int, int, int]) -> str:
    parts = list(value)
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return ".".join(str(part) for part in parts)


def _normalise_architecture(value: str) -> str:
    aliases = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}
    normalised = aliases.get(value.lower(), value.lower())
    if normalised not in _MACHO_CPU_TYPES:
        raise NativeCompatibilityError(f"unsupported expected architecture: {value!r}")
    return normalised


def _require_range(data: bytes, start: int, size: int, what: str) -> None:
    if start < 0 or size < 0 or start > len(data) or size > len(data) - start:
        raise NativeCompatibilityError(f"truncated {what}")


def _unpack(data: bytes, fmt: str, offset: int, what: str) -> tuple[object, ...]:
    size = struct.calcsize(fmt)
    _require_range(data, offset, size, what)
    try:
        return struct.unpack_from(fmt, data, offset)
    except struct.error as exc:
        raise NativeCompatibilityError(f"malformed {what}") from exc


def _macho_cputype(data: bytes, endian: str, offset: int) -> int:
    return int(_unpack(data, endian + "I", offset, "Mach-O CPU type")[0])


def _validate_macho_slice(data: bytes, architecture: str) -> None:
    if len(data) < 4:
        raise NativeCompatibilityError("Mach-O binary is truncated")
    magic_bytes = data[:4]
    formats = {
        b"\xcf\xfa\xed\xfe": ("<", 32),
        b"\xfe\xed\xfa\xcf": (">", 32),
        b"\xce\xfa\xed\xfe": ("<", 28),
        b"\xfe\xed\xfa\xce": (">", 28),
    }
    parsed = formats.get(magic_bytes)
    if parsed is None:
        raise NativeCompatibilityError("unrecognized Mach-O slice magic")
    endian, header_size = parsed
    cputype = _macho_cputype(data, endian, 4)
    expected = _MACHO_CPU_TYPES[architecture]
    if cputype != expected:
        raise NativeCompatibilityError(
            f"Mach-O architecture mismatch: expected {architecture}, cputype 0x{cputype:x}"
        )
    ncmds = int(_unpack(data, endian + "I", 16, "Mach-O header")[0])
    sizeofcmds = int(_unpack(data, endian + "I", 20, "Mach-O header")[0])
    _require_range(data, header_size, sizeofcmds, "Mach-O load commands")
    cursor = header_size
    found_macos_version = False
    versions: list[tuple[int, int, int]] = []
    for _ in range(ncmds):
        cmd, command_size = (
            int(value) for value in _unpack(data, endian + "II", cursor, "Mach-O load command")
        )
        if command_size < 8 or cursor + command_size > header_size + sizeofcmds:
            raise NativeCompatibilityError("malformed Mach-O load command size")
        if cmd == 0x32:  # LC_BUILD_VERSION
            if command_size < 24:
                raise NativeCompatibilityError("truncated LC_BUILD_VERSION command")
            platform, minos = (
                int(value) for value in _unpack(data, endian + "II", cursor + 8, "LC_BUILD_VERSION")
            )
            if platform == 1:  # PLATFORM_MACOS
                found_macos_version = True
                versions.append(_version(minos))
        elif cmd == 0x24:  # LC_VERSION_MIN_MACOSX
            if command_size < 16:
                raise NativeCompatibilityError("truncated LC_VERSION_MIN_MACOSX command")
            minos = int(_unpack(data, endian + "I", cursor + 8, "LC_VERSION_MIN_MACOSX")[0])
            found_macos_version = True
            versions.append(_version(minos))
        cursor += command_size
    if cursor != header_size + sizeofcmds:
        raise NativeCompatibilityError("Mach-O load command table is malformed")
    if not found_macos_version:
        raise NativeCompatibilityError("Mach-O has no macOS deployment version metadata")
    for version in versions:
        if version > POLICY.macos_max:
            raise NativeCompatibilityError(
                f"Mach-O macOS minimum {_version_text(version)} exceeds "
                f"the supported {_version_text(POLICY.macos_max)} baseline"
            )


def _validate_macho(data: bytes, architecture: str) -> None:
    magic = data[:4]
    fat_formats = {
        b"\xca\xfe\xba\xbe": (">", 20),
        b"\xbe\xba\xfe\xca": ("<", 20),
        b"\xca\xfe\xba\xbf": (">", 32),
        b"\xbf\xba\xfe\xca": ("<", 32),
    }
    fat = fat_formats.get(magic)
    if fat is None:
        _validate_macho_slice(data, architecture)
        return
    endian, entry_size = fat
    nfat_arch = int(_unpack(data, endian + "I", 4, "Mach-O fat header")[0])
    _require_range(data, 8, nfat_arch * entry_size, "Mach-O fat architecture table")
    expected = _MACHO_CPU_TYPES[architecture]
    matches: list[tuple[int, int]] = []
    for index in range(nfat_arch):
        offset = 8 + index * entry_size
        cputype = _macho_cputype(data, endian, offset)
        if entry_size == 20:
            slice_offset, slice_size = (
                int(value)
                for value in _unpack(data, endian + "II", offset + 8, "Mach-O fat architecture")
            )
        else:
            slice_offset, slice_size = (
                int(value)
                for value in _unpack(data, endian + "QQ", offset + 8, "Mach-O fat architecture")
            )
        _require_range(data, slice_offset, slice_size, "Mach-O fat slice")
        if cputype == expected:
            matches.append((slice_offset, slice_size))
    if len(matches) != 1:
        raise NativeCompatibilityError(
            f"Mach-O fat binary does not contain exactly one {architecture} slice"
        )
    offset, size = matches[0]
    _validate_macho_slice(data[offset : offset + size], architecture)


@dataclass(frozen=True)
class _ElfSection:
    section_type: int
    offset: int
    size: int
    link: int
    entry_size: int


def _elf_sections(data: bytes, endian: str, elf_class: int) -> tuple[list[_ElfSection], int]:
    if elf_class == 2:
        shoff = int(_unpack(data, endian + "Q", 40, "ELF header")[0])
        shentsize = int(_unpack(data, endian + "H", 58, "ELF header")[0])
        shnum = int(_unpack(data, endian + "H", 60, "ELF header")[0])
        shstrndx = int(_unpack(data, endian + "H", 62, "ELF header")[0])
        section_format = endian + "IIQQQQIIQQ"
    else:
        shoff, shentsize, shnum, shstrndx = (
            int(_unpack(data, endian + "I", 32, "ELF header")[0]),
            int(_unpack(data, endian + "H", 46, "ELF header")[0]),
            int(_unpack(data, endian + "H", 48, "ELF header")[0]),
            int(_unpack(data, endian + "H", 50, "ELF header")[0]),
        )
        section_format = endian + "IIIIIIIIII"
    expected_size = struct.calcsize(section_format)
    if shentsize != expected_size or shnum == 0:
        raise NativeCompatibilityError("ELF section header metadata is missing or malformed")
    _require_range(data, shoff, shentsize * shnum, "ELF section headers")
    sections: list[_ElfSection] = []
    for index in range(shnum):
        values = _unpack(data, section_format, shoff + index * shentsize, "ELF section header")
        if elf_class == 2:
            _, section_type, _, _, offset, size, link, _, _, entry_size = values
        else:
            _, section_type, _, _, offset, size, link, _, _, entry_size = values
        section = _ElfSection(int(section_type), int(offset), int(size), int(link), int(entry_size))
        if section.section_type != 8:  # SHT_NOBITS has no file data.
            _require_range(data, section.offset, section.size, "ELF section")
        if section.link >= shnum:
            raise NativeCompatibilityError("ELF section link is out of range")
        sections.append(section)
    if shstrndx >= shnum:
        raise NativeCompatibilityError("ELF section name table index is out of range")
    return sections, shnum


def _read_c_string(data: bytes, offset: int, what: str) -> str:
    if offset < 0 or offset >= len(data):
        raise NativeCompatibilityError(f"{what} string offset is out of range")
    end = data.find(b"\0", offset)
    if end < 0:
        raise NativeCompatibilityError(f"unterminated {what} string")
    try:
        return data[offset:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise NativeCompatibilityError(f"{what} string is not ASCII") from exc


def _version_names(data: bytes, endian: str, sections: list[_ElfSection]) -> set[str]:
    verneed_indices = [
        index for index, section in enumerate(sections) if section.section_type == 0x6FFFFFFE
    ]
    versym_indices = [
        index for index, section in enumerate(sections) if section.section_type == 0x6FFFFFFF
    ]
    if not verneed_indices or len(versym_indices) != 1:
        raise NativeCompatibilityError("ELF GNU symbol version metadata is missing")
    versym = sections[versym_indices[0]]
    if versym.size == 0 or versym.size % 2 or versym.entry_size not in (0, 2):
        raise NativeCompatibilityError("ELF GNU symbol version table is malformed")
    dynstr_index: int | None = None
    names: set[str] = set()
    for index in verneed_indices:
        section = sections[index]
        if section.link >= len(sections) or sections[section.link].section_type != 3:
            raise NativeCompatibilityError("ELF version requirement string table is malformed")
        if dynstr_index is None:
            dynstr_index = section.link
        elif dynstr_index != section.link:
            raise NativeCompatibilityError(
                "ELF version requirements use inconsistent string tables"
            )
        section_data = data[section.offset : section.offset + section.size]
        cursor = 0
        seen_offsets: set[int] = set()
        while cursor < len(section_data):
            if cursor in seen_offsets:
                raise NativeCompatibilityError("ELF version requirement list loops")
            seen_offsets.add(cursor)
            if len(section_data) - cursor < 16:
                raise NativeCompatibilityError("ELF version requirement is truncated")
            vn_version, vn_cnt, vn_file, vn_aux, vn_next = _unpack(
                section_data, endian + "HHIII", cursor, "ELF version requirement"
            )
            if vn_version == 0 or vn_cnt == 0 or vn_aux == 0:
                raise NativeCompatibilityError("ELF version requirement is malformed")
            string_table = sections[dynstr_index]
            string_data = data[string_table.offset : string_table.offset + string_table.size]
            _read_c_string(string_data, int(vn_file), "ELF version library")
            aux_cursor = cursor + int(vn_aux)
            aux_seen: set[int] = set()
            for auxiliary_index in range(int(vn_cnt)):
                if (
                    aux_cursor in aux_seen
                    or aux_cursor < cursor
                    or aux_cursor + 16 > len(section_data)
                ):
                    raise NativeCompatibilityError("ELF version auxiliary list is malformed")
                aux_seen.add(aux_cursor)
                _, _, _, vna_name, vna_next = _unpack(
                    section_data, endian + "IHHII", aux_cursor, "ELF version auxiliary"
                )
                names.add(_read_c_string(string_data, int(vna_name), "ELF version"))
                next_aux = int(vna_next)
                if auxiliary_index + 1 == int(vn_cnt):
                    if next_aux != 0:
                        raise NativeCompatibilityError("ELF version auxiliary count mismatch")
                elif next_aux == 0:
                    raise NativeCompatibilityError("ELF version auxiliary count mismatch")
                aux_cursor += next_aux
            next_requirement = int(vn_next)
            if next_requirement == 0:
                cursor = len(section_data)
            else:
                cursor += next_requirement
                if cursor <= 0 or cursor >= len(section_data):
                    raise NativeCompatibilityError(
                        "ELF version requirement next offset is malformed"
                    )
    return names


def _validate_elf(data: bytes, architecture: str) -> None:
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise NativeCompatibilityError("unrecognized ELF binary")
    elf_class = data[4]
    data_encoding = data[5]
    if elf_class not in (1, 2) or data_encoding not in (1, 2):
        raise NativeCompatibilityError("ELF class or byte order is malformed")
    endian = "<" if data_encoding == 1 else ">"
    machine = int(_unpack(data, endian + "H", 18, "ELF header")[0])
    if machine != _ELF_MACHINES[architecture]:
        raise NativeCompatibilityError(
            f"ELF architecture mismatch: expected {architecture}, machine {machine}"
        )
    if elf_class != 2:
        raise NativeCompatibilityError("ELF native plugin must be a 64-bit binary")
    names = _version_names(data, endian, _elf_sections(data, endian, elf_class)[0])
    if not names:
        raise NativeCompatibilityError("ELF has no parsed symbol version requirements")
    glibc: list[tuple[int, int, int]] = []
    glibcxx: list[tuple[int, int, int]] = []
    for name in names:
        if name.startswith("GLIBC_"):
            match = _GLIBC_RE.fullmatch(name)
            if match is None:
                raise NativeCompatibilityError(f"unparseable GLIBC version metadata: {name}")
            glibc.append(tuple(int(part or 0) for part in match.groups()))
        elif name.startswith("GLIBCXX_"):
            match = _GLIBCXX_RE.fullmatch(name)
            if match is None:
                raise NativeCompatibilityError(f"unparseable GLIBCXX version metadata: {name}")
            glibcxx.append(tuple(int(part or 0) for part in match.groups()))
    if not glibc or not glibcxx:
        raise NativeCompatibilityError("ELF is missing GLIBC or GLIBCXX version requirements")
    max_glibc = max(glibc)
    if max_glibc > POLICY.linux_glibc_max:
        raise NativeCompatibilityError(
            f"ELF GLIBC minimum {_version_text(max_glibc)} exceeds "
            f"the supported {_version_text(POLICY.linux_glibc_max)} baseline"
        )
    max_glibcxx = max(glibcxx)
    if max_glibcxx > POLICY.linux_glibcxx_max:
        raise NativeCompatibilityError(
            f"ELF GLIBCXX minimum {_version_text(max_glibcxx)} exceeds "
            f"the supported {_version_text(POLICY.linux_glibcxx_max)} baseline"
        )


def _validate_pe(data: bytes, architecture: str) -> None:
    if len(data) < 64 or data[:2] != b"MZ":
        raise NativeCompatibilityError("unrecognized PE binary")
    pe_offset = int(_unpack(data, "<I", 0x3C, "PE DOS header")[0])
    _require_range(data, pe_offset, 6, "PE header")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise NativeCompatibilityError("malformed PE signature")
    machine = int(_unpack(data, "<H", pe_offset + 4, "PE COFF header")[0])
    if machine != _PE_MACHINES[architecture]:
        raise NativeCompatibilityError(
            f"PE architecture mismatch: expected {architecture}, machine 0x{machine:x}"
        )


def validate_binary_bytes(
    data: bytes,
    *,
    runtime_os: str,
    architecture: str,
    label: str = "native plugin",
) -> None:
    """Validate one native Jieba library from bytes, independent of host OS."""

    if not data:
        raise NativeCompatibilityError(f"{label} is empty")
    architecture = _normalise_architecture(architecture)
    try:
        if runtime_os == "macos":
            _validate_macho(data, architecture)
        elif runtime_os == "linux":
            _validate_elf(data, architecture)
        elif runtime_os == "windows":
            _validate_pe(data, architecture)
        else:
            raise NativeCompatibilityError(f"unsupported native runtime OS: {runtime_os!r}")
    except NativeCompatibilityError as exc:
        raise NativeCompatibilityError(f"{label}: {exc}") from exc


def validate_binary_path(
    path: Path,
    *,
    runtime_os: str,
    architecture: str,
) -> None:
    """Validate a native library on disk."""

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise NativeCompatibilityError(f"native plugin cannot be read: {path}") from exc
    validate_binary_bytes(
        data,
        runtime_os=runtime_os,
        architecture=architecture,
        label=str(path),
    )

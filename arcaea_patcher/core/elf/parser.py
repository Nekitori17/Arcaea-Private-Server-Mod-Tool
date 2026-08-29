import struct
from typing import List, Optional, Tuple

from arcaea_patcher.core.elf.models import ProgramHeader, SectionHeader


class ElfParser:
    """Robust 32-bit and 64-bit ELF parser for symbol resolution."""

    SHT_NULL = 0
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHT_NOBITS = 8
    SHT_DYNSYM = 11

    SHN_UNDEF = 0
    SHN_XINDEX = 0xFFFF

    PT_LOAD = 1

    def __init__(self, data: bytearray):
        self.data = data

        if len(self.data) < 52 or not self.data.startswith(b"\x7fELF"):
            raise ValueError("Invalid ELF magic header.")

        self.ei_class = self.data[4]  # 1 = 32-bit, 2 = 64-bit
        self.ei_data = self.data[5]   # 1 = little-endian
        self.is_64bit = self.ei_class == 2
        self.endian_prefix = "<" if self.ei_data == 1 else ">"

        min_header_size = 64 if self.is_64bit else 52
        if len(self.data) < min_header_size:
            raise ValueError("ELF header is too small.")

        self.e_machine = struct.unpack_from(
            f"{self.endian_prefix}H",
            self.data,
            0x12,
        )[0]

        self.e_phoff = 0
        self.e_shoff = 0
        self.e_phentsize = 0
        self.e_phnum = 0
        self.e_shentsize = 0
        self.e_shnum = 0
        self.e_shstrndx = 0

        self.sections: List[SectionHeader] = []
        self.program_headers: List[ProgramHeader] = []

        self._parse_headers()

    def _parse_headers(self) -> None:
        """Parse ELF header, program headers, and section headers."""
        if self.is_64bit:
            self.e_phoff = struct.unpack_from(
                f"{self.endian_prefix}Q",
                self.data,
                0x20,
            )[0]

            self.e_shoff = struct.unpack_from(
                f"{self.endian_prefix}Q",
                self.data,
                0x28,
            )[0]

            self.e_phentsize, self.e_phnum = struct.unpack_from(
                f"{self.endian_prefix}HH",
                self.data,
                0x36,
            )

            self.e_shentsize, self.e_shnum, self.e_shstrndx = struct.unpack_from(
                f"{self.endian_prefix}HHH",
                self.data,
                0x3A,
            )
        else:
            self.e_phoff = struct.unpack_from(
                f"{self.endian_prefix}I",
                self.data,
                0x1C,
            )[0]

            self.e_shoff = struct.unpack_from(
                f"{self.endian_prefix}I",
                self.data,
                0x20,
            )[0]

            self.e_phentsize, self.e_phnum = struct.unpack_from(
                f"{self.endian_prefix}HH",
                self.data,
                0x2A,
            )

            self.e_shentsize, self.e_shnum, self.e_shstrndx = struct.unpack_from(
                f"{self.endian_prefix}HHH",
                self.data,
                0x2E,
            )

        self._fix_extended_section_numbers()
        self._parse_program_headers()
        self._parse_section_headers()

    def _fix_extended_section_numbers(self) -> None:
        """
        Handle ELF extended section numbering.

        If e_shnum is 0, the real section count is stored in sh_size
        of section header 0.

        If e_shstrndx is SHN_XINDEX, the real section name string table
        index is stored in sh_link of section header 0.
        """
        if self.e_shoff == 0 or self.e_shentsize == 0:
            return

        if self.e_shnum != 0 and self.e_shstrndx != self.SHN_XINDEX:
            return

        expected_shentsize = 64 if self.is_64bit else 40
        section0_offset = self.e_shoff

        if section0_offset + expected_shentsize > len(self.data):
            return

        if self.is_64bit:
            sh_size = struct.unpack_from(
                f"{self.endian_prefix}Q",
                self.data,
                section0_offset + 0x20,
            )[0]

            sh_link = struct.unpack_from(
                f"{self.endian_prefix}I",
                self.data,
                section0_offset + 0x28,
            )[0]
        else:
            sh_size = struct.unpack_from(
                f"{self.endian_prefix}I",
                self.data,
                section0_offset + 0x14,
            )[0]

            sh_link = struct.unpack_from(
                f"{self.endian_prefix}I",
                self.data,
                section0_offset + 0x18,
            )[0]

        if self.e_shnum == 0:
            self.e_shnum = int(sh_size)

        if self.e_shstrndx == self.SHN_XINDEX:
            self.e_shstrndx = int(sh_link)

    def _parse_program_headers(self) -> None:
        """Parse program headers."""
        self.program_headers = []

        if self.e_phoff == 0 or self.e_phnum == 0 or self.e_phentsize == 0:
            return

        expected_phentsize = 56 if self.is_64bit else 32
        if self.e_phentsize < expected_phentsize:
            return

        for i in range(self.e_phnum):
            offset = self.e_phoff + (i * self.e_phentsize)

            if offset + expected_phentsize > len(self.data):
                break

            if self.is_64bit:
                (
                    p_type,
                    p_flags,
                    p_offset,
                    p_vaddr,
                    p_paddr,
                    p_filesz,
                    p_memsz,
                    p_align,
                ) = struct.unpack_from(
                    f"{self.endian_prefix}IIQQQQQQ",
                    self.data,
                    offset,
                )
            else:
                (
                    p_type,
                    p_offset,
                    p_vaddr,
                    p_paddr,
                    p_filesz,
                    p_memsz,
                    p_flags,
                    p_align,
                ) = struct.unpack_from(
                    f"{self.endian_prefix}IIIIIIII",
                    self.data,
                    offset,
                )

            self.program_headers.append(
                ProgramHeader(
                    p_type=p_type,
                    p_offset=p_offset,
                    p_vaddr=p_vaddr,
                    p_paddr=p_paddr,
                    p_filesz=p_filesz,
                    p_memsz=p_memsz,
                    p_flags=p_flags,
                    p_align=p_align,
                )
            )

    def _parse_section_headers(self) -> None:
        """Parse section headers."""
        self.sections = []

        if self.e_shoff == 0 or self.e_shnum == 0 or self.e_shentsize == 0:
            return

        expected_shentsize = 64 if self.is_64bit else 40
        if self.e_shentsize < expected_shentsize:
            return

        for i in range(self.e_shnum):
            offset = self.e_shoff + (i * self.e_shentsize)

            if offset + expected_shentsize > len(self.data):
                break

            if self.is_64bit:
                (
                    name,
                    sh_type,
                    flags,
                    addr,
                    sh_offset,
                    size,
                    link,
                    info,
                    addralign,
                    entsize,
                ) = struct.unpack_from(
                    f"{self.endian_prefix}IIQQQQIIQQ",
                    self.data,
                    offset,
                )
            else:
                (
                    name,
                    sh_type,
                    flags,
                    addr,
                    sh_offset,
                    size,
                    link,
                    info,
                    addralign,
                    entsize,
                ) = struct.unpack_from(
                    f"{self.endian_prefix}IIIIIIIIII",
                    self.data,
                    offset,
                )

            self.sections.append(
                SectionHeader(
                    name_idx=name,
                    sh_type=sh_type,
                    sh_flags=flags,
                    sh_addr=addr,
                    sh_offset=sh_offset,
                    sh_size=size,
                    sh_link=link,
                    sh_info=info,
                    sh_addralign=addralign,
                    sh_entsize=entsize,
                )
            )

    def _get_string(self, strtab_offset: int, strtab_size: int, index: int) -> str:
        """Read a NUL-terminated string from a string table."""
        if strtab_offset >= len(self.data) or index >= strtab_size:
            return ""

        start = strtab_offset + index
        max_end = min(strtab_offset + strtab_size, len(self.data))

        if start >= max_end:
            return ""

        end = self.data.find(b"\x00", start, max_end)
        if end == -1:
            end = max_end

        return self.data[start:end].decode("ascii", errors="replace")

    def _get_shstrtab_section(self) -> Optional[SectionHeader]:
        """Get the section header string table section."""
        if self.e_shstrndx >= len(self.sections):
            return None

        return self.sections[self.e_shstrndx]

    def _get_section_name(self, section: SectionHeader) -> str:
        """Get section name from section header string table."""
        shstrtab = self._get_shstrtab_section()
        if shstrtab is None:
            return ""

        return self._get_string(
            shstrtab.sh_offset,
            shstrtab.sh_size,
            section.name_idx,
        )

    def _find_symbol_sections(self) -> List[SectionHeader]:
        """
        Find symbol table sections.

        Priority:
        1. SHT_DYNSYM sections
        2. Sections named .dynsym
        3. SHT_SYMTAB sections
        """
        candidates: List[SectionHeader] = []

        for section in self.sections:
            if section.sh_type == self.SHT_DYNSYM:
                candidates.append(section)

        if candidates:
            return candidates

        for section in self.sections:
            if self._get_section_name(section) == ".dynsym":
                candidates.append(section)

        if candidates:
            return candidates

        for section in self.sections:
            if section.sh_type == self.SHT_SYMTAB:
                candidates.append(section)

        return candidates

    def vaddr_to_file_offset(self, vaddr: int) -> Optional[int]:
        """
        Convert a virtual address to a file offset using PT_LOAD segments.

        This is usually more reliable than using only section headers.
        """
        for ph in self.program_headers:
            if ph.p_type != self.PT_LOAD or ph.p_filesz == 0:
                continue

            if ph.p_vaddr <= vaddr < ph.p_vaddr + ph.p_filesz:
                offset = ph.p_offset + (vaddr - ph.p_vaddr)

                if 0 <= offset < len(self.data):
                    return offset

        return None

    def _section_vaddr_to_file_offset(self, vaddr: int) -> Optional[int]:
        """
        Fallback helper to convert a virtual address to file offset
        using section headers.
        """
        for section in self.sections:
            if section.sh_type == self.SHT_NOBITS or section.sh_size == 0:
                continue

            if section.sh_addr <= vaddr < section.sh_addr + section.sh_size:
                offset = section.sh_offset + (vaddr - section.sh_addr)

                if 0 <= offset < len(self.data):
                    return offset

        return None

    def find_symbol_location(self, symbol_name: str) -> Optional[Tuple[int, bool, int]]:
        """
        Find a symbol and return:

            (file_offset, is_thumb, symbol_size)

        For ARM32, is_thumb is True if the symbol value has the Thumb bit set.
        """
        symbol_sections = self._find_symbol_sections()
        if not symbol_sections:
            return None

        expected_entry_size = 24 if self.is_64bit else 16

        for sym_sec in symbol_sections:
            if sym_sec.sh_link >= len(self.sections):
                continue

            strtab_sec = self.sections[sym_sec.sh_link]

            entry_size = sym_sec.sh_entsize
            if entry_size < expected_entry_size:
                entry_size = expected_entry_size

            if entry_size <= 0 or sym_sec.sh_size < entry_size:
                continue

            count = sym_sec.sh_size // entry_size

            for i in range(count):
                sym_offset = sym_sec.sh_offset + (i * entry_size)

                if sym_offset + expected_entry_size > len(self.data):
                    break

                if self.is_64bit:
                    (
                        st_name,
                        st_info,
                        st_other,
                        st_shndx,
                        st_value,
                        st_size,
                    ) = struct.unpack_from(
                        f"{self.endian_prefix}IBBHQQ",
                        self.data,
                        sym_offset,
                    )
                else:
                    (
                        st_name,
                        st_value,
                        st_size,
                        st_info,
                        st_other,
                        st_shndx,
                    ) = struct.unpack_from(
                        f"{self.endian_prefix}IIIBBH",
                        self.data,
                        sym_offset,
                    )

                if st_shndx == self.SHN_UNDEF or st_value == 0:
                    continue

                name = self._get_string(
                    strtab_sec.sh_offset,
                    strtab_sec.sh_size,
                    st_name,
                )

                if name != symbol_name:
                    continue

                value = st_value
                is_thumb = False

                # ARM32 symbols may use the lowest bit to mark Thumb code.
                if not self.is_64bit and self.e_machine == 0x28:
                    is_thumb = bool(value & 1)
                    value &= ~1

                file_offset = self.vaddr_to_file_offset(value)
                if file_offset is None:
                    file_offset = self._section_vaddr_to_file_offset(value)

                if file_offset is None or file_offset < 0 or file_offset >= len(self.data):
                    continue

                return file_offset, is_thumb, int(st_size)

        return None

    def find_symbol_file_offset(self, symbol_name: str) -> Optional[int]:
        """
        Backward-compatible helper.

        Returns only the file offset of the requested symbol.
        """
        location = self.find_symbol_location(symbol_name)
        if location is None:
            return None

        return location[0]
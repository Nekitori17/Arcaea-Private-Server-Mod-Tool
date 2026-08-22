from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Dict, List, Optional
from arcaea_patcher.utils.logger import logger


@dataclass
class SectionHeader:
    name_idx: int
    sh_type: int
    sh_flags: int
    sh_addr: int
    sh_offset: int
    sh_size: int
    sh_link: int
    sh_info: int
    sh_addralign: int
    sh_entsize: int


class ElfParser:
    """Robust 32-bit and 64-bit ELF parser for symbol resolution."""

    def __init__(self, data: bytearray):
        self.data = data
        if not self.data.startswith(b"\x7fELF"):
            raise ValueError("Invalid ELF magic header.")

        self.ei_class = self.data[4]  # 1 = 32-bit, 2 = 64-bit
        self.ei_data = self.data[5]   # 1 = Little-endian
        self.is_64bit = self.ei_class == 2
        self.endian_prefix = "<" if self.ei_data == 1 else ">"

        self.e_machine = struct.unpack_from(
            f"{self.endian_prefix}H", self.data, 0x12
        )[0]
        self._parse_headers()

    def _parse_headers(self) -> None:
        if self.is_64bit:
            (
                self.e_shoff,
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(
                f"{self.endian_prefix}QxxxxxxHHH", self.data, 0x28
            )
        else:
            self.e_shoff = struct.unpack_from(
                f"{self.endian_prefix}I", self.data, 0x20
            )[0]
            (
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(
                f"{self.endian_prefix}HHH", self.data, 0x2E
            )

        self.sections: List[SectionHeader] = []
        for i in range(self.e_shnum):
            off = self.e_shoff + (i * self.e_shentsize)
            if self.is_64bit:
                (
                    name,
                    stype,
                    flags,
                    addr,
                    offset,
                    size,
                    link,
                    info,
                    align,
                    entsize,
                ) = struct.unpack_from(f"{self.endian_prefix}IIQQQQIIQQ", self.data, off)
            else:
                (
                    name,
                    stype,
                    flags,
                    addr,
                    offset,
                    size,
                    link,
                    info,
                    align,
                    entsize,
                ) = struct.unpack_from(f"{self.endian_prefix}IIIIIIIIII", self.data, off)

            self.sections.append(
                SectionHeader(
                    name_idx=name,
                    sh_type=stype,
                    sh_flags=flags,
                    sh_addr=addr,
                    sh_offset=offset,
                    sh_size=size,
                    sh_link=link,
                    sh_info=info,
                    sh_addralign=align,
                    sh_entsize=entsize,
                )
            )

    def _get_string(self, strtab_offset: int, strtab_size: int, index: int) -> str:
        if index >= strtab_size:
            return ""
        end = self.data.find(b"\x00", strtab_offset + index)
        if end == -1:
            end = strtab_offset + strtab_size
        return self.data[strtab_offset + index : end].decode("ascii", errors="replace")

    def find_symbol_file_offset(self, symbol_name: str) -> Optional[int]:
        shstrtab_sec = self.sections[self.e_shstrndx]
        dynsym_sec: Optional[SectionHeader] = None

        for sec in self.sections:
            sec_name = self._get_string(
                shstrtab_sec.sh_offset, shstrtab_sec.sh_size, sec.name_idx
            )
            if sec_name == ".dynsym":
                dynsym_sec = sec
                break

        if not dynsym_sec or dynsym_sec.sh_link >= len(self.sections):
            return None

        dynstr_sec = self.sections[dynsym_sec.sh_link]
        entry_size = 24 if self.is_64bit else 16
        count = dynsym_sec.sh_size // entry_size

        for i in range(count):
            sym_off = dynsym_sec.sh_offset + (i * entry_size)
            if self.is_64bit:
                st_name, st_info, st_other, st_shndx, st_value, _ = struct.unpack_from(
                    f"{self.endian_prefix}IBBHQQ", self.data, sym_off
                )
            else:
                st_name, st_value, _, st_info, st_other, st_shndx = struct.unpack_from(
                    f"{self.endian_prefix}IIIBBH", self.data, sym_off
                )

            # Skip undefined symbols
            if st_shndx == 0 or st_value == 0:
                continue

            name = self._get_string(
                dynstr_sec.sh_offset, dynstr_sec.sh_size, st_name
            )
            if name == symbol_name:
                # Map virtual address (VMA) to file offset
                for sec in self.sections:
                    if sec.sh_addr <= st_value < (sec.sh_addr + sec.sh_size):
                        return sec.sh_offset + (st_value - sec.sh_addr)
                return st_value

        return None


class NativeLibraryPatcher:
    """Applies binary patches to bypass native OpenSSL verification."""

    ARM64_RET = b"\xC0\x03\x5F\xD6"  # RET
    ARM64_RET_TRUE = b"\x20\x00\x80\x52" + ARM64_RET  # MOV W0, #1; RET

    ARM32_RET = b"\x1E\xFF\x2F\xE1"  # BX LR
    ARM32_RET_TRUE = b"\x01\x00\xA0\xE3" + ARM32_RET  # MOV R0, #1; BX LR

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def patch_ssl_pinning(self) -> bool:
        with open(self.library_path, "rb") as f:
            data = bytearray(f.read())

        try:
            parser = ElfParser(data)
        except Exception as e:
            logger.warn(f"Failed to parse {self.library_path.name}: {e}")
            return False

        if parser.e_machine == 0xB7:  # AArch64
            ret_void = self.ARM64_RET
            ret_true = self.ARM64_RET_TRUE
        elif parser.e_machine == 0x28:  # ARM32
            ret_void = self.ARM32_RET
            ret_true = self.ARM32_RET_TRUE
        else:
            logger.warn(f"Unsupported architecture machine: {hex(parser.e_machine)}")
            return False

        patched = False
        # Symbols to return void
        for sym in ["SSL_CTX_set_verify", "SSL_set_verify"]:
            offset = parser.find_symbol_file_offset(sym)
            if offset is not None:
                data[offset : offset + len(ret_void)] = ret_void
                logger.success(f"[{self.library_path.parent.name}] Patched {sym} (void)")
                patched = True

        # Symbols to return success (1)
        for sym in ["X509_verify_cert"]:
            offset = parser.find_symbol_file_offset(sym)
            if offset is not None:
                data[offset : offset + len(ret_true)] = ret_true
                logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 1)")
                patched = True

        if patched:
            with open(self.library_path, "wb") as f:
                f.write(data)

        return patched
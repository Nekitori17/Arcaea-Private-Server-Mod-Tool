from dataclasses import dataclass
from pathlib import Path
import struct
from typing import List, Optional, Tuple
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
        self.ei_data = self.data[5]   # 1 = Little-endian, 2 = Big-endian
        if self.ei_class not in (1, 2):
            raise ValueError(f"Unsupported ELF class: {self.ei_class}")
        if self.ei_data not in (1, 2):
            raise ValueError(f"Unsupported ELF data encoding: {self.ei_data}")
        self.is_64bit = self.ei_class == 2
        self.endian_prefix = "<" if self.ei_data == 1 else ">"

        self.e_machine = struct.unpack_from(
            f"{self.endian_prefix}H", self.data, 0x12
        )[0]
        self._parse_headers()

    def _parse_headers(self) -> None:
        if self.is_64bit:
            self.e_shoff = struct.unpack_from(f"{self.endian_prefix}Q", self.data, 0x28)[0]
            (
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(f"{self.endian_prefix}HHH", self.data, 0x3A)
        else:
            self.e_shoff = struct.unpack_from(f"{self.endian_prefix}I", self.data, 0x20)[0]
            (
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(f"{self.endian_prefix}HHH", self.data, 0x2E)

        self.sections: List[SectionHeader] = []
        if self.e_shoff == 0 or self.e_shnum == 0:
            return
        if self.e_shoff + (self.e_shnum * self.e_shentsize) > len(self.data):
            raise ValueError("Section header table is out of bounds.")
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

    def find_symbol_file_offset(
        self, symbol_name: str
    ) -> Optional[Tuple[int, bool]]:
        """Locates `symbol_name` in .dynsym.

        Returns ``(file_offset, is_thumb)`` or ``None`` when the symbol is not
        defined in .dynsym. On ARM, bit 0 of st_value marks a Thumb function:
        the bit is stripped from the offset and reported to the caller so it
        can emit Thumb instructions instead of ARM ones.
        """
        if not self.sections or self.e_shstrndx >= len(self.sections):
            return None

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

            if st_shndx == 0 or st_value == 0:
                continue

            name = self._get_string(dynstr_sec.sh_offset, dynstr_sec.sh_size, st_name)
            if name != symbol_name:
                continue

            is_thumb = False
            value = st_value
            if self.e_machine == 0x28 and (value & 1):  # ARM Thumb bit
                is_thumb = True
                value &= ~1

            for sec in self.sections:
                if sec.sh_addr <= value < (sec.sh_addr + sec.sh_size):
                    return sec.sh_offset + (value - sec.sh_addr), is_thumb

            # Never fall back to st_value itself: it is a virtual address, not a
            # file offset, and patching there would corrupt unrelated bytes.
            return None

        return None


class NativeLibraryPatcher:
    """Applies binary domain replacement and OpenSSL verification bypasses."""

    ARM64_RET = b"\xC0\x03\x5F\xD6"
    ARM64_RET_1 = b"\x20\x00\x80\x52" + ARM64_RET       # MOV W0, #1; RET
    ARM64_RET_0 = b"\x00\x00\x80\x52" + ARM64_RET       # MOV W0, #0; RET (X509_V_OK)

    ARM32_RET = b"\x1E\xFF\x2F\xE1"
    ARM32_RET_1 = b"\x01\x00\xA0\xE3" + ARM32_RET       # MOV R0, #1; BX LR
    ARM32_RET_0 = b"\x00\x00\xA0\xE3" + ARM32_RET       # MOV R0, #0; BX LR

    ARM32_THUMB_RET = b"\x70\x47"                          # bx lr
    ARM32_THUMB_RET_1 = b"\x01\x20" + ARM32_THUMB_RET      # movs r0, #1; bx lr
    ARM32_THUMB_RET_0 = b"\x00\x20" + ARM32_THUMB_RET      # movs r0, #0; bx lr

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def _apply_patches(
        self,
        data: bytearray,
        parser: ElfParser,
        symbols: List[str],
        arm_bytes: bytes,
        thumb_bytes: bytes,
        description: str,
    ) -> int:
        """Neutralises every symbol in `symbols` in place.

        Uses `thumb_bytes` for Thumb functions and `arm_bytes` otherwise.
        Returns how many symbols are in the patched state.
        """
        abi = self.library_path.parent.name
        applied = 0
        for symbol in symbols:
            found = parser.find_symbol_file_offset(symbol)
            if found is None:
                logger.warn(f"[{abi}] {symbol} not found in .dynsym; skipped")
                continue
            offset, is_thumb = found
            patch = thumb_bytes if is_thumb else arm_bytes
            end = offset + len(patch)
            if end > len(data):
                logger.warn(f"[{abi}] {symbol}: offset 0x{offset:x} is out of file bounds; skipped")
                continue
            if data[offset:end] == patch:
                logger.detail(f"[{abi}] {symbol} already patched ({description})")
                applied += 1
                continue
            data[offset:end] = patch
            suffix = ", Thumb" if is_thumb else ""
            logger.success(f"[{abi}] Patched {symbol} ({description}{suffix})")
            applied += 1
        return applied

    def patch_ssl_bypass(self) -> bool:
        """Applies the OpenSSL/BoringSSL verification bypasses in place."""
        abi = self.library_path.parent.name
        try:
            with open(self.library_path, "rb") as f:
                data = bytearray(f.read())

            parser = ElfParser(data)

            if parser.e_machine == 0xB7:  # AArch64
                arm_void, thumb_void = self.ARM64_RET, self.ARM64_RET
                arm_true, thumb_true = self.ARM64_RET_1, self.ARM64_RET_1
                arm_zero, thumb_zero = self.ARM64_RET_0, self.ARM64_RET_0
            elif parser.e_machine == 0x28:  # ARM32
                arm_void, thumb_void = self.ARM32_RET, self.ARM32_THUMB_RET
                arm_true, thumb_true = self.ARM32_RET_1, self.ARM32_THUMB_RET_1
                arm_zero, thumb_zero = self.ARM32_RET_0, self.ARM32_THUMB_RET_0
            else:
                logger.warn(f"[{abi}] Unsupported architecture: {hex(parser.e_machine)}")
                return False

            applied = 0
            applied += self._apply_patches(
                data,
                parser,
                ["SSL_CTX_set_verify", "SSL_set_verify", "SSL_CTX_set_custom_verify"],
                arm_void,
                thumb_void,
                "void",
            )
            applied += self._apply_patches(
                data, parser, ["X509_verify_cert"], arm_true, thumb_true, "return 1"
            )
            applied += self._apply_patches(
                data,
                parser,
                ["SSL_get_verify_result"],
                arm_zero,
                thumb_zero,
                "return 0 / X509_V_OK",
            )

            if applied == 0:
                logger.warn(f"[{abi}] No SSL symbols patched; file left untouched")
                return False

            with open(self.library_path, "wb") as f:
                f.write(data)
            logger.detail(f"[{abi}] Saved {applied} patched symbol(s) into {self.library_path.name}")
            return True

        except Exception as e:
            logger.warn(f"Failed to process {self.library_path.name} in {abi}: {e}")
            return False

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
    """32-bit and 64-bit ELF parser for resolving dynamic symbol file offsets."""

    def __init__(self, data: bytearray):
        self.data = data
        if not self.data.startswith(b"\x7fELF"):
            raise ValueError("Invalid ELF magic header")

        self.ei_class = self.data[4]  # 1 = 32-bit, 2 = 64-bit
        self.ei_data = self.data[5]   # 1 = Little-endian, 2 = Big-endian
        if self.ei_class not in (1, 2) or self.ei_data not in (1, 2):
            raise ValueError("Unsupported ELF class or endianness")

        self.is_64bit = self.ei_class == 2
        self.endian_prefix = "<" if self.ei_data == 1 else ">"
        self.e_machine = struct.unpack_from(f"{self.endian_prefix}H", self.data, 0x12)[0]
        self._parse_headers()

    def _parse_headers(self) -> None:
        fmt = f"{self.endian_prefix}QHHH" if self.is_64bit else f"{self.endian_prefix}IHHH"
        off = 0x28 if self.is_64bit else 0x20
        shoff_data = struct.unpack_from(fmt[:2], self.data, off)
        self.e_shoff = shoff_data[0]
        meta_off = 0x3A if self.is_64bit else 0x2E
        self.e_shentsize, self.e_shnum, self.e_shstrndx = struct.unpack_from(
            f"{self.endian_prefix}HHH", self.data, meta_off
        )

        self.sections: List[SectionHeader] = []
        if self.e_shoff == 0 or self.e_shnum == 0:
            return

        sec_fmt = f"{self.endian_prefix}IIQQQQIIQQ" if self.is_64bit else f"{self.endian_prefix}IIIIIIIIII"
        for i in range(self.e_shnum):
            entry_off = self.e_shoff + (i * self.e_shentsize)
            fields = struct.unpack_from(sec_fmt, self.data, entry_off)
            self.sections.append(SectionHeader(*fields))

    def _get_string(self, strtab_offset: int, strtab_size: int, index: int) -> str:
        if index >= strtab_size:
            return ""
        end = self.data.find(b"\x00", strtab_offset + index)
        if end == -1:
            end = strtab_offset + strtab_size
        return self.data[strtab_offset + index : end].decode("ascii", errors="replace")

    def find_symbol_file_offset(self, symbol_name: str) -> Optional[Tuple[int, bool]]:
        """Locates symbol in .dynsym; returns (file_offset, is_thumb) or None."""
        if not self.sections or self.e_shstrndx >= len(self.sections):
            return None

        shstrtab = self.sections[self.e_shstrndx]
        dynsym_sec: Optional[SectionHeader] = None
        for sec in self.sections:
            if self._get_string(shstrtab.sh_offset, shstrtab.sh_size, sec.name_idx) == ".dynsym":
                dynsym_sec = sec
                break

        if not dynsym_sec or dynsym_sec.sh_link >= len(self.sections):
            return None

        dynstr = self.sections[dynsym_sec.sh_link]
        entry_size = 24 if self.is_64bit else 16
        count = dynsym_sec.sh_size // entry_size

        for i in range(count):
            sym_off = dynsym_sec.sh_offset + (i * entry_size)
            if self.is_64bit:
                st_name, _, _, st_shndx, st_value, _ = struct.unpack_from(
                    f"{self.endian_prefix}IBBHQQ", self.data, sym_off
                )
            else:
                st_name, st_value, _, _, _, st_shndx = struct.unpack_from(
                    f"{self.endian_prefix}IIIBBH", self.data, sym_off
                )

            if st_shndx == 0 or st_value == 0:
                continue

            if self._get_string(dynstr.sh_offset, dynstr.sh_size, st_name) != symbol_name:
                continue

            is_thumb = False
            val = st_value
            if self.e_machine == 0x28 and (val & 1):
                is_thumb = True
                val &= ~1

            for sec in self.sections:
                if sec.sh_addr <= val < (sec.sh_addr + sec.sh_size):
                    return sec.sh_offset + (val - sec.sh_addr), is_thumb

            return None
        return None


class NativeLibraryPatcher:
    """Patches OpenSSL / BoringSSL verification symbols in native .so binaries."""

    ARM64_RET = b"\xC0\x03\x5F\xD6"
    ARM64_RET_1 = b"\x20\x00\x80\x52" + ARM64_RET
    ARM64_RET_0 = b"\x00\x00\x80\x52" + ARM64_RET

    ARM32_RET = b"\x1E\xFF\x2F\xE1"
    ARM32_RET_1 = b"\x01\x00\xA0\xE3" + ARM32_RET
    ARM32_RET_0 = b"\x00\x00\xA0\xE3" + ARM32_RET

    ARM32_THUMB_RET = b"\x70\x47"
    ARM32_THUMB_RET_1 = b"\x01\x20" + ARM32_THUMB_RET
    ARM32_THUMB_RET_0 = b"\x00\x20" + ARM32_THUMB_RET

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
        abi = self.library_path.parent.name
        applied = 0
        for symbol in symbols:
            found = parser.find_symbol_file_offset(symbol)
            if found is None:
                logger.warn(f"[{abi}] {symbol} not in .dynsym; skipped")
                continue

            offset, is_thumb = found
            patch = thumb_bytes if is_thumb else arm_bytes
            end = offset + len(patch)
            if end > len(data):
                logger.warn(f"[{abi}] {symbol} offset out of bounds; skipped")
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
        """Applies verification bypass machine instructions to target shared library."""
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
                logger.warn(f"[{abi}] Unsupported ELF machine architecture: {hex(parser.e_machine)}")
                return False

            applied = 0
            applied += self._apply_patches(
                data, parser,
                ["SSL_CTX_set_verify", "SSL_set_verify", "SSL_CTX_set_custom_verify"],
                arm_void, thumb_void, "void",
            )
            applied += self._apply_patches(
                data, parser, ["X509_verify_cert"], arm_true, thumb_true, "return 1"
            )
            applied += self._apply_patches(
                data, parser, ["SSL_CTX_set_cert_verify_callback"], arm_void, thumb_void, "void"
            )
            applied += self._apply_patches(
                data, parser, ["SSL_set1_host"], arm_true, thumb_true, "return 1"
            )
            applied += self._apply_patches(
                data, parser, ["SSL_get_verify_result"], arm_zero, thumb_zero, "return 0"
            )
            applied += self._apply_patches(
                data, parser, ["X509_check_host"], arm_true, thumb_true, "return 1"
            )

            if applied == 0:
                logger.warn(f"[{abi}] No SSL symbols found to patch in {self.library_path.name}")
                return False

            with open(self.library_path, "wb") as f:
                f.write(data)
            logger.detail(f"[{abi}] Saved {applied} patched symbol(s) into {self.library_path.name}")
            return True

        except Exception as e:
            logger.warn(f"Failed to patch {self.library_path.name} in {abi}: {e}")
            return False

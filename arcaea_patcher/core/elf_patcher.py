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
        if self.e_shstrndx >= len(self.sections):
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

            name = self._get_string(
                dynstr_sec.sh_offset, dynstr_sec.sh_size, st_name
            )
            if name == symbol_name:
                for sec in self.sections:
                    if sec.sh_addr <= st_value < (sec.sh_addr + sec.sh_size):
                        return sec.sh_offset + (st_value - sec.sh_addr)
                return st_value

        return None


class NativeLibraryPatcher:
    """Applies binary domain replacement and OpenSSL verification bypasses."""

    ARM64_RET = b"\xC0\x03\x5F\xD6"
    ARM64_RET_1 = b"\x20\x00\x80\x52" + ARM64_RET       # MOV W0, #1; RET
    ARM64_RET_0 = b"\x00\x00\x80\x52" + ARM64_RET       # MOV W0, #0; RET (X509_V_OK)

    ARM32_RET = b"\x1E\xFF\x2F\xE1"
    ARM32_RET_1 = b"\x01\x00\xA0\xE3" + ARM32_RET       # MOV R0, #1; BX LR
    ARM32_RET_0 = b"\x00\x00\xA0\xE3" + ARM32_RET       # MOV R0, #0; BX LR

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def _replace_exact_bytes(self, data: bytearray, old_pattern: bytes, new_host: str) -> int:
        """Replaces exact byte patterns padded with null bytes to preserve binary offset alignment."""
        new_bytes = new_host.encode("utf-8")
        if len(new_bytes) > len(old_pattern):
            logger.warn(
                f"[{self.library_path.parent.name}] Value '{new_host}' ({len(new_bytes)}B) "
                f"exceeds limit ({len(old_pattern)}B) for '{old_pattern.decode(errors='ignore')}'. Skipping."
            )
            return 0

        padded_replacement = new_bytes + b"\x00" * (len(old_pattern) - len(new_bytes))
        count = data.count(old_pattern)
        if count > 0:
            data[:] = data.replace(old_pattern, padded_replacement)
        return count

    def patch_domains_and_ssl(
        self,
        api_host: Optional[str] = None,
        auth_host: Optional[str] = None,
        custom_mappings: Optional[Dict[str, str]] = None,
    ) -> bool:
        try:
            with open(self.library_path, "rb") as f:
                data = bytearray(f.read())

            parser = ElfParser(data)

            if parser.e_machine == 0xB7:  # AArch64
                ret_void = self.ARM64_RET
                ret_true = self.ARM64_RET_1
                ret_zero = self.ARM64_RET_0
            elif parser.e_machine == 0x28:  # ARM32
                ret_void = self.ARM32_RET
                ret_true = self.ARM32_RET_1
                ret_zero = self.ARM32_RET_0
            else:
                logger.warn(f"[{self.library_path.parent.name}] Unsupported architecture: {hex(parser.e_machine)}")
                return False

            patched = False

            # 1. URL Domain Replacements (Matching test.py exact replace)
            if api_host:
                c1 = self._replace_exact_bytes(data, b"arcapi-v4.lowiro.com", api_host)
                c2 = self._replace_exact_bytes(data, b"arcapi-v3.lowiro.com", api_host)
                if c1 > 0 or c2 > 0:
                    logger.success(f"[{self.library_path.parent.name}] Replaced {c1 + c2} arcapi-v4/v3 -> {api_host}")
                    patched = True

            if auth_host:
                c3 = self._replace_exact_bytes(data, b"auth-v2.lowiro.com", auth_host)
                c4 = self._replace_exact_bytes(data, b"auth.lowiro.com", auth_host)
                c5 = self._replace_exact_bytes(data, b"arcaea.lowiro.com", auth_host)
                if c3 > 0 or c4 > 0 or c5 > 0:
                    logger.success(f"[{self.library_path.parent.name}] Replaced {c3 + c4 + c5} auth-v2/auth -> {auth_host}")
                    patched = True

            if custom_mappings:
                for old_h, new_h in custom_mappings.items():
                    cnt = self._replace_exact_bytes(data, old_h.encode("utf-8"), new_h)
                    if cnt > 0:
                        logger.success(f"[{self.library_path.parent.name}] Replaced {cnt} custom mapping(s): '{old_h}' -> '{new_h}'")
                        patched = True

            # 2. Native SSL Pinning Bypass (OpenSSL / BoringSSL)
            for sym in ["SSL_CTX_set_verify", "SSL_set_verify", "SSL_CTX_set_custom_verify"]:
                offset = parser.find_symbol_file_offset(sym)
                if offset is not None:
                    data[offset : offset + len(ret_void)] = ret_void
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (void)")
                    patched = True

            for sym in ["X509_verify_cert"]:
                offset = parser.find_symbol_file_offset(sym)
                if offset is not None:
                    data[offset : offset + len(ret_true)] = ret_true
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 1)")
                    patched = True

            for sym in ["SSL_get_verify_result"]:
                offset = parser.find_symbol_file_offset(sym)
                if offset is not None:
                    data[offset : offset + len(ret_zero)] = ret_zero
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 0 / X509_V_OK)")
                    patched = True

            if patched:
                with open(self.library_path, "wb") as f:
                    f.write(data)

            return patched

        except Exception as e:
            logger.warn(f"Failed to process {self.library_path.name} in {self.library_path.parent.name}: {e}")
            return False
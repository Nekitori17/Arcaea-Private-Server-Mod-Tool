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
    """Applies binary & assembly patches to bypass native OpenSSL verification & reconstruct std::string domains."""

    ARM64_NOP = b"\x1F\x20\x03\xD5"                      # NOP
    ARM64_RET = b"\xC0\x03\x5F\xD6"                      # RET
    ARM64_RET_1 = b"\x20\x00\x80\x52" + ARM64_RET       # MOV W0, #1; RET (Success)
    ARM64_RET_0 = b"\x00\x00\x80\x52" + ARM64_RET       # MOV W0, #0; RET (X509_V_OK)

    ARM32_RET = b"\x1E\xFF\x2F\xE1"                      # BX LR
    ARM32_RET_1 = b"\x01\x00\xA0\xE3" + ARM32_RET       # MOV R0, #1; BX LR
    ARM32_RET_0 = b"\x00\x00\xA0\xE3" + ARM32_RET       # MOV R0, #0; BX LR

    def __init__(self, library_path: Path):
        self.library_path = library_path

    @staticmethod
    def _encode_arm64_movz(rd: int, imm16: int) -> bytes:
        """Encodes `MOVZ Wd, #imm16` instruction for AArch64."""
        opcode = 0x52800000 | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)
        return opcode.to_bytes(4, "little")

    def _patch_arm64_api_sso_string(self, data: bytearray, new_host: str) -> bool:
        """
        Patches the inline `std::string` constructor for arcapi-v4 at .text:017C4218.
        Original pattern: MOV W8, #0x28 (len 20*2=40)
        """
        new_bytes = new_host.encode("utf-8")
        str_len = len(new_bytes)
        if str_len > 20:
            logger.warn(f"API Host '{new_host}' ({str_len}B) exceeds 20-byte SSO limit. Skipping.")
            return False

        # Pattern: MOV W8, #0x28 (0x08, 0x05, 0x80, 0x52)
        pattern = b"\x08\x05\x80\x52"
        idx = data.find(pattern)
        if idx == -1:
            logger.warn("Could not find arcapi-v4 SSO Assembly sequence.")
            return False

        # 1. Patch MOV W8, #(str_len * 2)
        data[idx : idx + 4] = self._encode_arm64_movz(8, str_len * 2)

        # 2. Patch remaining bytes
        if str_len <= 16:
            # NOP out MOV W9 (#0x6D6F632E) at idx+4 and STUR W9 at idx+16
            data[idx + 4 : idx + 8] = self.ARM64_NOP
            data[idx + 16 : idx + 20] = self.ARM64_NOP
        else:
            # Encode remaining 1..4 bytes into W9
            rem = new_bytes[16:str_len].ljust(4, b"\x00")
            imm32 = int.from_bytes(rem, "little")
            data[idx + 4 : idx + 8] = self._encode_arm64_movz(9, imm32 & 0xFFFF)

        logger.success(f"[{self.library_path.parent.name}] Patched arcapi-v4 SSO Assembly (New Length: {str_len})")
        return True

    def _patch_arm64_auth_sso_string(self, data: bytearray, new_host: str) -> bool:
        """
        Patches the inline `std::string` constructor for auth-v2 at .text:017C44E8.
        Original pattern: MOV W8, #0x24 (len 18*2=36)
        """
        new_bytes = new_host.encode("utf-8")
        str_len = len(new_bytes)
        if str_len > 18:
            logger.warn(f"Auth Host '{new_host}' ({str_len}B) exceeds 18-byte SSO limit. Skipping.")
            return False

        # Pattern: MOV W8, #0x24 (0x88, 0x04, 0x80, 0x52)
        pattern = b"\x88\x04\x80\x52"
        idx = data.find(pattern)
        if idx == -1:
            logger.warn("Could not find auth-v2 SSO Assembly sequence.")
            return False

        # 1. Patch MOV W8, #(str_len * 2)
        data[idx : idx + 4] = self._encode_arm64_movz(8, str_len * 2)

        # 2. Patch remaining bytes
        if str_len <= 16:
            # NOP out MOV W9 (#0x6D6F) at idx+4 and STURH W9 at idx+16
            data[idx + 4 : idx + 8] = self.ARM64_NOP
            data[idx + 16 : idx + 20] = self.ARM64_NOP
        else:
            # Encode remaining 1..2 bytes into W9
            rem = new_bytes[16:str_len].ljust(2, b"\x00")
            imm16 = int.from_bytes(rem, "little")
            data[idx + 4 : idx + 8] = self._encode_arm64_movz(9, imm16)

        logger.success(f"[{self.library_path.parent.name}] Patched auth-v2 SSO Assembly (New Length: {str_len})")
        return True

    def _replace_string_padded(self, data: bytearray, old_str: str, new_str: str) -> bool:
        """Finds null-terminated string in .rodata and pads with null bytes."""
        old_bytes = old_str.encode("utf-8") + b"\x00"
        new_bytes = new_str.encode("utf-8")

        if len(new_bytes) >= len(old_bytes):
            return False

        replacement = new_bytes + b"\x00" * (len(old_bytes) - len(new_bytes))
        count = 0
        start = 0
        while True:
            idx = data.find(old_bytes, start)
            if idx == -1:
                break
            data[idx : idx + len(old_bytes)] = replacement
            count += 1
            start = idx + len(old_bytes)

        if count > 0:
            logger.success(
                f"[{self.library_path.parent.name}] Replaced {count} string(s) in .rodata: '{old_str}' -> '{new_str}'"
            )
            return True
        return False

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
                is_arm64 = True
            elif parser.e_machine == 0x28:  # ARM32
                ret_void = self.ARM32_RET
                ret_true = self.ARM32_RET_1
                ret_zero = self.ARM32_RET_0
                is_arm64 = False
            else:
                logger.warn(f"[{self.library_path.parent.name}] Unsupported architecture: {hex(parser.e_machine)}")
                return False

            patched = False

            # 1. Patch Domain Strings (.rodata + Assembly SSO construction)
            if api_host:
                self._replace_string_padded(data, "arcapi-v4.lowiro.com", api_host)
                self._replace_string_padded(data, "arcapi-v3.lowiro.com", api_host)
                if is_arm64:
                    self._patch_arm64_api_sso_string(data, api_host)
                patched = True

            if auth_host:
                self._replace_string_padded(data, "auth-v2.lowiro.com", auth_host)
                self._replace_string_padded(data, "auth.lowiro.com", auth_host)
                self._replace_string_padded(data, "arcaea.lowiro.com", auth_host)
                if is_arm64:
                    self._patch_arm64_auth_sso_string(data, auth_host)
                patched = True

            if custom_mappings:
                for old_h, new_h in custom_mappings.items():
                    if self._replace_string_padded(data, old_h, new_h):
                        patched = True

            # 2. Patch OpenSSL / BoringSSL Functions
            # Return Void
            for sym in ["SSL_CTX_set_verify", "SSL_set_verify", "SSL_CTX_set_custom_verify"]:
                offset = parser.find_symbol_file_offset(sym)
                if offset is not None:
                    data[offset : offset + len(ret_void)] = ret_void
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (void)")
                    patched = True

            # Return Success (1)
            for sym in ["X509_verify_cert"]:
                offset = parser.find_symbol_file_offset(sym)
                if offset is not None:
                    data[offset : offset + len(ret_true)] = ret_true
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 1)")
                    patched = True

            # Return X509_V_OK (0) for libcurl SSL_get_verify_result
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
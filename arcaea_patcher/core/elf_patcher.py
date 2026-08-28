from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Optional, Tuple
from arcaea_patcher.utils.logger import logger


@dataclass
class ProgramHeader:
    p_type: int
    p_offset: int
    p_vaddr: int
    p_memsz: int


class ElfParser:
    """Robust 32-bit and 64-bit ELF parser resistant to section stripping.
    Resolves symbols strictly via Program Headers (PT_DYNAMIC & PT_LOAD)."""

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
                self.e_phoff,
                self.e_shoff,
                self.e_flags,
                self.e_ehsize,
                self.e_phentsize,
                self.e_phnum,
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(f"{self.endian_prefix}QQIHHHHHH", self.data, 0x20)
        else:
            (
                self.e_phoff,
                self.e_shoff,
                self.e_flags,
                self.e_ehsize,
                self.e_phentsize,
                self.e_phnum,
                self.e_shentsize,
                self.e_shnum,
                self.e_shstrndx,
            ) = struct.unpack_from(f"{self.endian_prefix}IIIHHHHHH", self.data, 0x1C) # FIX: Change IIII to III

        self.program_headers = []
        for i in range(self.e_phnum):
            off = self.e_phoff + (i * self.e_phentsize)
            if self.is_64bit:
                (
                    p_type, p_flags, p_offset, p_vaddr, p_paddr,
                    p_filesz, p_memsz, p_align
                ) = struct.unpack_from(f"{self.endian_prefix}IIQQQQQQ", self.data, off)
            else:
                (
                    p_type, p_offset, p_vaddr, p_paddr,
                    p_filesz, p_memsz, p_flags, p_align
                ) = struct.unpack_from(f"{self.endian_prefix}IIIIIIII", self.data, off)

            self.program_headers.append(
                ProgramHeader(
                    p_type=p_type,
                    p_offset=p_offset,
                    p_vaddr=p_vaddr,
                    p_memsz=p_memsz
                )
            )

    def vaddr_to_offset(self, vaddr: int) -> Optional[int]:
        """Convert a virtual address to a file offset using PT_LOAD headers."""
        for ph in self.program_headers:
            if ph.p_type == 1:  # PT_LOAD
                if ph.p_vaddr <= vaddr < (ph.p_vaddr + ph.p_memsz):
                    return ph.p_offset + (vaddr - ph.p_vaddr)
        return None

    def _get_string(self, strtab_offset: int, index: int) -> str:
        end = self.data.find(b"\x00", strtab_offset + index)
        if end == -1:
            return ""
        return self.data[strtab_offset + index : end].decode("ascii", errors="ignore")

    def find_symbol_info(self, symbol_name: str) -> Optional[Tuple[int, bool]]:
        """Finds symbol in PT_DYNAMIC. Returns tuple(file_offset, is_thumb)."""
        dyn_ph = next((ph for ph in self.program_headers if ph.p_type == 2), None)
        if not dyn_ph:
            return None

        ent_sz = 16 if self.is_64bit else 8
        symtab_vaddr = None
        strtab_vaddr = None
        syment = 24 if self.is_64bit else 16

        # Parse DT Entries
        for i in range(dyn_ph.p_memsz // ent_sz):
            off = dyn_ph.p_offset + (i * ent_sz)
            if self.is_64bit:
                d_tag, d_val = struct.unpack_from(f"{self.endian_prefix}QQ", self.data, off)
            else:
                d_tag, d_val = struct.unpack_from(f"{self.endian_prefix}II", self.data, off)

            if d_tag == 2:    # DT_SYMTAB
                symtab_vaddr = d_val
            elif d_tag == 5:  # DT_STRTAB
                strtab_vaddr = d_val
            elif d_tag == 11: # DT_SYMENT
                syment = d_val
            elif d_tag == 0:  # DT_NULL
                break

        if symtab_vaddr is None or strtab_vaddr is None:
            return None

        symtab_off = self.vaddr_to_offset(symtab_vaddr)
        strtab_off = self.vaddr_to_offset(strtab_vaddr)

        if symtab_off is None or strtab_off is None:
            return None

        # Determine reasonable limit for symbol parsing to prevent out of bounds
        max_entries = 50000
        if symtab_off < strtab_off:
            estimated = (strtab_off - symtab_off) // syment
            if estimated > 0:
                max_entries = min(max_entries, estimated)

        for i in range(max_entries):
            sym_off = symtab_off + (i * syment)
            if sym_off + syment > len(self.data):
                break

            if self.is_64bit:
                st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
                    f"{self.endian_prefix}IBBHQQ", self.data, sym_off
                )
            else:
                st_name, st_value, st_size, st_info, st_other, st_shndx = struct.unpack_from(
                    f"{self.endian_prefix}IIIBBH", self.data, sym_off
                )

            if st_shndx == 0 or st_value == 0:
                continue

            name = self._get_string(strtab_off, st_name)
            if name == symbol_name:
                # ARM32 Thumb check (LSB == 1 means Thumb-2)
                is_thumb = (not self.is_64bit) and ((st_value & 1) != 0)
                # Clear the architecture bit to get the actual instruction address
                actual_addr = st_value & ~1
                func_off = self.vaddr_to_offset(actual_addr)
                if func_off is not None:
                    return (func_off, is_thumb)

        return None


class NativeLibraryPatcher:
    """Applies binary domain replacement and OpenSSL verification bypasses."""

    # ARM64: AArch64 instructions are always 4 bytes
    ARM64_RET_VOID = b"\xC0\x03\x5F\xD6"
    ARM64_RET_TRUE = b"\x20\x00\x80\x52\xC0\x03\x5F\xD6" # MOV W0, #1; RET
    ARM64_RET_ZERO = b"\x00\x00\x80\x52\xC0\x03\x5F\xD6" # MOV W0, #0; RET

    # ARM32 (ARM Mode): 4 bytes per instruction
    ARM32_RET_VOID = b"\x1E\xFF\x2F\xE1"
    ARM32_RET_TRUE = b"\x01\x00\xA0\xE3\x1E\xFF\x2F\xE1" # MOV R0, #1; BX LR
    ARM32_RET_ZERO = b"\x00\x00\xA0\xE3\x1E\xFF\x2F\xE1" # MOV R0, #0; BX LR

    # ARM32 (Thumb Mode): 2 or 4 bytes per instruction
    THUMB_RET_VOID = b"\x70\x47\xC0\x46"                 # BX LR; NOP
    THUMB_RET_TRUE = b"\x01\x20\x70\x47"                 # MOVS R0, #1; BX LR
    THUMB_RET_ZERO = b"\x00\x20\x70\x47"                 # MOVS R0, #0; BX LR

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def _get_patch(self, machine: int, is_thumb: bool, ret_type: str) -> bytes:
        if machine == 0xB7:  # AArch64
            if ret_type == 'void': return self.ARM64_RET_VOID
            if ret_type == 'true': return self.ARM64_RET_TRUE
            if ret_type == 'zero': return self.ARM64_RET_ZERO
        elif machine == 0x28:  # ARM32
            if is_thumb:
                if ret_type == 'void': return self.THUMB_RET_VOID
                if ret_type == 'true': return self.THUMB_RET_TRUE
                if ret_type == 'zero': return self.THUMB_RET_ZERO
            else:
                if ret_type == 'void': return self.ARM32_RET_VOID
                if ret_type == 'true': return self.ARM32_RET_TRUE
                if ret_type == 'zero': return self.ARM32_RET_ZERO
        return b""

    def patch_ssl_bypass(self) -> bool:
        """Applies binary OpenSSL / BoringSSL verification bypasses."""
        try:
            with open(self.library_path, "rb") as f:
                data = bytearray(f.read())

            parser = ElfParser(data)
            if parser.e_machine not in (0xB7, 0x28):
                logger.warn(f"[{self.library_path.parent.name}] Unsupported architecture: {hex(parser.e_machine)}")
                return False

            patched = False

            # Native SSL Pinning Bypass (OpenSSL / BoringSSL)
            for sym in ["SSL_CTX_set_verify", "SSL_set_verify", "SSL_CTX_set_custom_verify"]:
                sym_info = parser.find_symbol_info(sym)
                if sym_info:
                    offset, is_thumb = sym_info
                    patch = self._get_patch(parser.e_machine, is_thumb, 'void')
                    data[offset : offset + len(patch)] = patch
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (void)")
                    patched = True

            for sym in ["X509_verify_cert"]:
                sym_info = parser.find_symbol_info(sym)
                if sym_info:
                    offset, is_thumb = sym_info
                    patch = self._get_patch(parser.e_machine, is_thumb, 'true')
                    data[offset : offset + len(patch)] = patch
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 1)")
                    patched = True

            for sym in ["SSL_get_verify_result"]:
                sym_info = parser.find_symbol_info(sym)
                if sym_info:
                    offset, is_thumb = sym_info
                    patch = self._get_patch(parser.e_machine, is_thumb, 'zero')
                    data[offset : offset + len(patch)] = patch
                    logger.success(f"[{self.library_path.parent.name}] Patched {sym} (return 0 / X509_V_OK)")
                    patched = True

            if patched:
                with open(self.library_path, "wb") as f:
                    f.write(data)

            return patched

        except Exception as e:
            logger.warn(f"Failed to process {self.library_path.name} in {self.library_path.parent.name}: {e}")
            return False
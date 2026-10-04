from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

from arcaea_patcher.core.elf_patcher import ElfParser
from arcaea_patcher.utils.logger import logger

EM_ARM = 0x28
EM_AARCH64 = 0xB7

ARCH_NAMES: Dict[int, str] = {
    EM_AARCH64: "AArch64",
    EM_ARM: "ARM32",
}

# Curl SSL-pin verifier prologue tail ("SSL: public key does not match pinned
# public key" reporting site). The tail is matched instead of the whole
# prologue so an already-patched entry point is still detectable: the patch
# offset is ``hit - len(stub)``. Each signature matches exactly one function
# per ABI.
VERIFIER_TAIL_SIGNATURES: Dict[int, bytes] = {
    EM_AARCH64: bytes.fromhex(
        "f85f02a9f65703a9f44f04a9fd430091ff0700f9420500b4"
    ),
    EM_ARM: bytes.fromhex(
        "0040a0e3000052e304408de50170a0115a40a01300005113"
    ),
}

# Early-exit stubs that force the verifier to report success (CURLE_OK == 0).
BYPASS_STUBS: Dict[int, bytes] = {
    EM_AARCH64: bytes.fromhex("00008052c0035fd6"),  # mov w0, #0 ; ret
    EM_ARM: bytes.fromhex("0000a0e31eff2fe1"),      # mov r0, #0 ; bx lr
}


class PinVerifierPatcher:
    """Applies an instruction-level bypass to curl's pinned-public-key check."""

    def __init__(self, library_path: Path):
        self.library_path = library_path

    @property
    def abi(self) -> str:
        return self.library_path.parent.name

    def _text_range(self, parser: ElfParser) -> Optional[Tuple[int, int]]:
        """Returns the ``.text`` (file_offset, file_end) span, if resolvable."""
        if not parser.sections or parser.e_shstrndx >= len(parser.sections):
            return None
        shstrtab = parser.sections[parser.e_shstrndx]
        for sec in parser.sections:
            name = parser._get_string(shstrtab.sh_offset, shstrtab.sh_size, sec.name_idx)
            if name == ".text":
                return sec.sh_offset, sec.sh_offset + sec.sh_size
        return None

    @staticmethod
    def _locate(data: bytearray, signature: bytes,
                bounds: Optional[Tuple[int, int]]) -> int:
        """Finds the signature, preferring the ``.text`` span when known."""
        if bounds is not None:
            hit = data.find(signature, bounds[0], bounds[1])
            if hit >= 0:
                return hit
        return data.find(signature)

    def patch(self) -> bool:
        """Patches the verifier in-place; returns True when patches are present."""
        try:
            with open(self.library_path, "rb") as f:
                data = bytearray(f.read())

            parser = ElfParser(data)
            tail = VERIFIER_TAIL_SIGNATURES.get(parser.e_machine)
            stub = BYPASS_STUBS.get(parser.e_machine)
            if tail is None or stub is None:
                logger.warn(
                    f"[{self.abi}] Unsupported ELF machine for pin bypass: "
                    f"{hex(parser.e_machine)}"
                )
                return False

            hit = self._locate(data, tail, self._text_range(parser))
            offset = hit - len(stub)
            if hit < 0 or offset < 0:
                logger.warn(
                    f"[{self.abi}] Pinned-pubkey verifier signature not found in "
                    f"{self.library_path.name}; skipped"
                )
                return False

            if data[offset:offset + len(stub)] == stub:
                logger.detail(f"[{self.abi}] Pinned-pubkey verifier already patched")
                return True

            data[offset:offset + len(stub)] = stub
            with open(self.library_path, "wb") as f:
                f.write(data)

            arch = ARCH_NAMES.get(parser.e_machine, hex(parser.e_machine))
            logger.success(
                f"[{self.abi}] Patched pinned-pubkey verifier ({arch}, return 0) "
                f"@ 0x{offset:X}"
            )
            return True

        except Exception as e:
            logger.warn(f"Failed to patch pinned-pubkey verifier in {self.abi}: {e}")
            return False
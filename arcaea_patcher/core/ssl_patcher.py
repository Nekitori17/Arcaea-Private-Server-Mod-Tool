from pathlib import Path

from arcaea_patcher.utils.logger import logger

from arcaea_patcher.core.elf.parser import ElfParser
from arcaea_patcher.core.opcodes import (
    ARM32_RET,
    ARM32_RET_0,
    ARM32_RET_1,
    ARM64_RET,
    ARM64_RET_0,
    ARM64_RET_1,
    THUMB_RET,
    THUMB_RET_0,
    THUMB_RET_1,
)


class NativeLibraryPatcher:
    """Applies native SSL verification bypass patches to an ELF library."""

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def _apply_patch(
        self,
        data: bytearray,
        offset: int,
        payload: bytes,
        symbol_name: str,
    ) -> bool:
        """
        Apply a patch safely.

        Returns True if the target bytes are already equal to the payload
        or if the payload was written successfully.
        """
        if offset is None or offset < 0:
            return False

        end = offset + len(payload)

        if end > len(data):
            logger.warn(
                f"[{self.library_path.parent.name}] Skip {symbol_name}: "
                f"patch out of bounds "
                f"(offset={hex(offset)}, payload_len={len(payload)}, file_size={len(data)})"
            )
            return False

        # Already patched.
        if data[offset:end] == payload:
            return True

        data[offset:end] = payload
        return True

    def patch_ssl_bypass(self) -> bool:
        """
        Patch common OpenSSL/BoringSSL verification functions.

        Patched symbols:
        - SSL_CTX_set_verify
        - SSL_set_verify
        - SSL_CTX_set_custom_verify
        - X509_verify_cert
        - SSL_get_verify_result
        """
        try:
            data = bytearray(self.library_path.read_bytes())
            parser = ElfParser(data)

            if parser.e_machine == 0xB7:
                arch = "arm64"
            elif parser.e_machine == 0x28:
                arch = "arm32"
            else:
                logger.warn(
                    f"[{self.library_path.parent.name}] "
                    f"Unsupported architecture: {hex(parser.e_machine)}"
                )
                return False

            def payload_for(kind: str, is_thumb: bool) -> bytes:
                """
                Select the correct payload for the target architecture.

                kind:
                - void: return immediately
                - true: return 1
                - zero: return 0
                """
                if arch == "arm64":
                    if kind == "void":
                        return ARM64_RET
                    if kind == "true":
                        return ARM64_RET_1
                    return ARM64_RET_0

                if is_thumb:
                    if kind == "void":
                        return THUMB_RET
                    if kind == "true":
                        return THUMB_RET_1
                    return THUMB_RET_0

                if kind == "void":
                    return ARM32_RET
                if kind == "true":
                    return ARM32_RET_1
                return ARM32_RET_0

            patched = False

            targets = [
                ("SSL_CTX_set_verify", "void"),
                ("SSL_set_verify", "void"),
                ("SSL_CTX_set_custom_verify", "void"),
                ("X509_verify_cert", "true"),
                ("SSL_get_verify_result", "zero"),
            ]

            for symbol_name, kind in targets:
                location = parser.find_symbol_location(symbol_name)

                if location is None:
                    continue

                offset, is_thumb, symbol_size = location
                payload = payload_for(kind, is_thumb)

                # If the symbol size is known and too small, skip patching
                # to avoid corrupting adjacent code.
                if symbol_size and symbol_size < len(payload):
                    logger.warn(
                        f"[{self.library_path.parent.name}] Skip {symbol_name}: "
                        f"symbol size {symbol_size} is smaller than payload size {len(payload)}"
                    )
                    continue

                if self._apply_patch(data, offset, payload, symbol_name):
                    mode = "ARM64" if arch == "arm64" else ("Thumb" if is_thumb else "ARM32")

                    logger.success(
                        f"[{self.library_path.parent.name}] "
                        f"Patched {symbol_name} ({kind}, {mode}) "
                        f"at file offset {hex(offset)}"
                    )

                    patched = True

            if patched:
                self.library_path.write_bytes(bytes(data))

            return patched

        except Exception as e:
            logger.error(
                f"Failed to process {self.library_path.name} "
                f"in {self.library_path.parent.name}: {e}"
            )
            return False
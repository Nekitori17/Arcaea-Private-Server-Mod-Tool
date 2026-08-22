from pathlib import Path
import tempfile
from typing import List, Tuple
from arcaea_patcher.config import PatchConfig
from arcaea_patcher.core.apk_toolchain import ApkToolchain
from arcaea_patcher.core.elf_patcher import NativeLibraryPatcher
from arcaea_patcher.core.manifest_patcher import ManifestAndSecurityPatcher
from arcaea_patcher.core.smali_patcher import SmaliPatcher
from arcaea_patcher.utils.logger import logger


class PatchPipeline:
    """Coordinates decompilation, patching, and recompilation phases."""

    def __init__(self, config: PatchConfig, toolchain: ApkToolchain):
        self.config = config
        self.toolchain = toolchain

    def execute(self) -> None:
        logger.header("Starting APK Patch Pipeline")

        if not self.config.input_apk.exists():
            raise FileNotFoundError(f"Target input APK does not exist: {self.config.input_apk}")

        with tempfile.TemporaryDirectory(prefix="apk_patcher_") as temp_dir:
            work_path = Path(temp_dir)
            decoded_dir = work_path / "decoded"
            unaligned_apk = work_path / "unaligned.apk"

            # Phase 1: Decompile
            logger.header("[1/5] Decompiling APK")
            self.toolchain.decompile(self.config.input_apk, decoded_dir)
            logger.success("APK successfully decoded.")

            # Phase 2: Network Security Config
            if self.config.inject_nsc:
                logger.header("[2/5] Injecting Network Security Config")
                nsc_patcher = ManifestAndSecurityPatcher(decoded_dir)
                nsc_patcher.inject_network_security_config()

            # Phase 3: Native Library Patching
            if self.config.patch_native_ssl:
                logger.header("[3/5] Patching Native Binaries (.so)")
                so_files = list(decoded_dir.glob("lib/**/libcocos2dcpp.so"))
                if not so_files:
                    logger.warn("No libcocos2dcpp.so binaries found.")
                for so_file in so_files:
                    patcher = NativeLibraryPatcher(so_file)
                    patcher.patch_ssl_pinning()

            # Phase 4: Smali / Java Bytecode Patching
            if self.config.patch_java_ssl or self.config.server.api_host or self.config.server.auth_host:
                logger.header("[4/5] Patching Java Bytecode")
                smali_patcher = SmaliPatcher(decoded_dir)
                if self.config.patch_java_ssl:
                    smali_patcher.patch_ssl_pinning()

                replacements: List[Tuple[str, str]] = []
                if self.config.server.api_host:
                    replacements.extend([
                        ("arcapi-v4.lowiro.com", self.config.server.api_host),
                        ("arcapi-v3.lowiro.com", self.config.server.api_host),
                    ])
                if self.config.server.auth_host:
                    replacements.extend([
                        ("auth-v2.lowiro.com", self.config.server.auth_host),
                        ("auth.lowiro.com", self.config.server.auth_host),
                        ("arcaea.lowiro.com", self.config.server.auth_host),
                    ])
                for old_h, new_h in self.config.server.custom_mappings.items():
                    replacements.append((old_h, new_h))

                if replacements:
                    smali_patcher.inject_domain_replacement(replacements)

            # Phase 5: Rebuild, Align, and Sign
            logger.header("[5/5] Rebuilding & Signing APK")
            self.toolchain.build(decoded_dir, unaligned_apk)
            logger.detail("Rebuilt APK with apktool.")

            self.config.output_apk.parent.mkdir(parents=True, exist_ok=True)
            self.toolchain.zipalign(unaligned_apk, self.config.output_apk)
            logger.detail("Aligned output package.")

            self.toolchain.sign(self.config.output_apk, self.config.signing)
            logger.success(f"Patched APK ready: {self.config.output_apk.resolve()}")
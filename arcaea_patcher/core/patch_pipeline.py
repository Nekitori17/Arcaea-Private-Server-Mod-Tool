from pathlib import Path
import shutil
import tempfile
from typing import Optional

from arcaea_patcher.config import PatchConfig
from arcaea_patcher.core.apk_toolchain import ApkToolchain
from arcaea_patcher.core.domain_patcher import DomainRoutingPatcher
from arcaea_patcher.core.elf_patcher import NativeLibraryPatcher
from arcaea_patcher.core.manifest_patcher import ManifestAndSecurityPatcher
from arcaea_patcher.core.pin_patcher import PinVerifierPatcher
from arcaea_patcher.core.smali_patcher import SmaliPatcher
from arcaea_patcher.utils.logger import logger


class PatchPipeline:
    """Coordinates decompilation, resource/bytecode/binary patching, and rebuild."""

    def __init__(
        self,
        config: PatchConfig,
        toolchain: ApkToolchain,
        templates_dir: Optional[Path] = None,
    ):
        self.config = config
        self.toolchain = toolchain
        self.templates_dir = templates_dir or (Path(__file__).parent.parent / "templates")

    def _merge_templates(self, decoded_dir: Path) -> int:
        """Copies pre-baked native libraries and smali classes into decoded APK."""
        if not self.templates_dir.is_dir():
            logger.warn(f"Templates directory not found: {self.templates_dir}")
            return 0

        copied = 0
        for src in sorted(self.templates_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(self.templates_dir)
            dst = decoded_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.detail(f"Merged template: {rel.as_posix()}")
            copied += 1
        return copied

    def _patch_native_binaries(self, decoded_dir: Path) -> None:
        """Applies instruction-level OpenSSL bypasses to all target native binaries."""
        so_files = list(decoded_dir.glob("lib/**/libcocos2dcpp.so"))
        if not so_files:
            logger.warn("No libcocos2dcpp.so found in decoded APK")
            return
        for so_file in so_files:
            patcher = NativeLibraryPatcher(so_file)
            patcher.patch_ssl_bypass()
            PinVerifierPatcher(so_file).patch()

    def execute(self) -> None:
        """Executes the full patching workflow."""
        logger.header("Starting APK Patch Pipeline")

        if not self.config.input_apk.is_file():
            raise FileNotFoundError(f"Input APK not found: {self.config.input_apk}")

        temp_dir = Path(tempfile.mkdtemp(prefix="apk_patcher_"))
        try:
            decoded_dir = temp_dir / "decoded"
            unaligned_apk = temp_dir / "unaligned.apk"

            # Phase 1: Decompile
            logger.header("[1/9] Decompiling APK")
            self.toolchain.decompile(self.config.input_apk, decoded_dir)
            logger.success("APK successfully decoded.")

            # Phase 2: Merge pre-baked templates
            logger.header("[2/9] Merging Baked Templates")
            merged = self._merge_templates(decoded_dir)
            if merged:
                logger.success(f"Merged {merged} template file(s) into decoded APK.")
            else:
                logger.warn("No template files merged (run complie.py if templates are missing).")

            # Phase 3: Manifest Modifications
            manifest_patcher = ManifestAndSecurityPatcher(decoded_dir)
            if self.config.package_name:
                logger.header("[3/9] Changing Package Name")
                manifest_patcher.change_package_name(self.config.package_name)

            # Phase 4: Network Security Config
            if self.config.inject_nsc:
                logger.header("[4/9] Injecting Network Security Config")
                manifest_patcher.inject_network_security_config()

            # Phase 5: Storage Access Framework Provider
            if self.config.feature_config.expose_internal_data:
                logger.header("[5/9] Injecting Storage Access Framework Provider")
                manifest_patcher.inject_documents_provider()

            # Phase 6: Dynamic Domain Routing
            if self.config.server.has_routing:
                logger.header("[6/9] Writing Domain Routing Config (domain.cfg)")
                domain_patcher = DomainRoutingPatcher(decoded_dir)
                domain_patcher.apply(self.config.server)

            # Phase 7: Native Binary Patching
            if self.config.patch_native_ssl:
                logger.header("[7/9] Patching Native Binaries (.so)")
                self._patch_native_binaries(decoded_dir)

            # Phase 8: Java Bytecode Patching
            if self.config.patch_java_ssl:
                logger.header("[8/9] Patching Java Bytecode")
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.patch_ssl_pinning()

            # Phase 9: Rebuild, Align, and Sign
            logger.header("[9/9] Rebuilding & Signing APK")
            self.toolchain.build(decoded_dir, unaligned_apk)
            logger.detail("Rebuilt APK with apktool.")

            self.config.output_apk.parent.mkdir(parents=True, exist_ok=True)
            self.toolchain.zipalign(unaligned_apk, self.config.output_apk)
            logger.detail("Aligned output package.")

            self.toolchain.sign(self.config.output_apk, self.config.signing)
            logger.success(f"Patched APK ready: {self.config.output_apk.resolve()}")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

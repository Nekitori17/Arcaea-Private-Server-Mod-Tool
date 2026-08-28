from pathlib import Path
import shutil
import tempfile
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

        temp_dir_path = tempfile.mkdtemp(prefix="apk_patcher_")
        work_path = Path(temp_dir_path)

        try:
            decoded_dir = work_path / "decoded"
            unaligned_apk = work_path / "unaligned.apk"

            # Phase 1: Decompile
            logger.header("[1/8] Decompiling APK")
            self.toolchain.decompile(self.config.input_apk, decoded_dir)
            logger.success("APK successfully decoded.")

            # Phase 2: Manifest & Network Security Config
            manifest_patcher = ManifestAndSecurityPatcher(decoded_dir)
            if self.config.package_name:
                logger.header("[2/8] Changing Package Name")
                manifest_patcher.change_package_name(self.config.package_name)

            if self.config.inject_nsc:
                logger.header("[3/8] Injecting Network Security Config")
                manifest_patcher.inject_network_security_config()

            if self.config.feature_config.expose_internal_data:
                logger.header("[4/8] Injecting Storage Access Framework Provider")
                manifest_patcher.inject_documents_provider()
                
                # Copy Smali template
                template_path = Path(__file__).parent.parent / "templates" / "InternalStorageProvider.smali"
                if template_path.exists():
                    dest_smali_dir = decoded_dir / "smali_classes2" / "moe" / "low" / "arc" / "custom"
                    dest_smali_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(template_path, dest_smali_dir / "InternalStorageProvider.smali")
                    logger.detail("Injected InternalStorageProvider.smali")
                else:
                    logger.warn("InternalStorageProvider.smali template not found!")

            # Phase 3: Native Binary Patching (SSL Bypass + Domain Redirection via Assembly & .rodata)
            logger.header("[5/8] Patching Native Binaries (.so)")
            so_files = list(decoded_dir.glob("lib/**/libcocos2dcpp.so"))
            if not so_files:
                logger.warn("No libcocos2dcpp.so binaries found.")
            for so_file in so_files:
                patcher = NativeLibraryPatcher(so_file)
                patcher.patch_domains_and_ssl(
                    api_host=self.config.server.api_host,
                    auth_host=self.config.server.auth_host,
                    custom_mappings=self.config.server.custom_mappings,
                )

            # Phase 4: Java Bytecode SSL Patching
            if self.config.patch_java_ssl:
                logger.header("[7/8] Patching Java Bytecode")
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.patch_ssl_pinning()

            # Phase 5: Rebuild, Align, and Sign
            logger.header("[8/8] Rebuilding & Signing APK")
            self.toolchain.build(decoded_dir, unaligned_apk)
            logger.detail("Rebuilt APK with apktool.")

            self.config.output_apk.parent.mkdir(parents=True, exist_ok=True)
            self.toolchain.zipalign(unaligned_apk, self.config.output_apk)
            logger.detail("Aligned output package.")

            self.toolchain.sign(self.config.output_apk, self.config.signing)
            logger.success(f"Patched APK ready: {self.config.output_apk.absolute()}")

        finally:
            try:
                shutil.rmtree(temp_dir_path, ignore_errors=True)
            except Exception:
                pass
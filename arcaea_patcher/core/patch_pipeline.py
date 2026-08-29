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

    def _get_target_smali_dir(self, decoded_dir: Path) -> Path:
        """Finds the optimal smali directory to inject custom classes."""
        smali_classes2 = decoded_dir / "smali_classes2"
        if smali_classes2.exists():
            return smali_classes2
        return decoded_dir / "smali"

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

            # Phase 3: Storage Access Framework Provider
            if self.config.feature_config.expose_internal_data:
                logger.header("[4/8] Injecting Storage Access Framework Provider")
                manifest_patcher.inject_documents_provider()
                
                # Copy Smali template (Tự động chọn thư mục smali)
                template_path = Path(__file__).parent.parent / "templates" / "InternalStorageProvider.smali"
                if template_path.exists():
                    target_smali_base = self._get_target_smali_dir(decoded_dir)
                    dest_smali_dir = target_smali_base / "moe" / "low" / "arc" / "custom"
                    dest_smali_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(template_path, dest_smali_dir / "InternalStorageProvider.smali")
                    logger.detail("Injected InternalStorageProvider.smali")
                else:
                    logger.warn("InternalStorageProvider.smali template not found!")

            # Phase 4: Dynamic Domain Routing via libneki.so (Native Hook)
            server_cfg = self.config.server
            has_domain_routing = bool(
                server_cfg and (server_cfg.api_host or server_cfg.auth_host or server_cfg.custom_mappings)
            )
            
            if has_domain_routing:
                logger.header("[5/8] Injecting Native Domain Redirection (libneki.so)")
                
                # Try to import constants; fall back if an error occurs.
                try:
                    from arcaea_patcher.constants import API_DOMAINS, AUTH_DOMAINS
                except ImportError:
                    API_DOMAINS = ["arcapi-v4.lowiro.com", "arcapi-v3.lowiro.com", "arcaea.lowiro.com"]
                    AUTH_DOMAINS = ["auth-v2.lowiro.com", "auth.lowiro.com"]

                domain_lines = []
                if self.config.server.api_host:
                    for d in API_DOMAINS:
                        domain_lines.append(f"{d}={self.config.server.api_host}")
                if self.config.server.auth_host:
                    for d in AUTH_DOMAINS:
                        domain_lines.append(f"{d}={self.config.server.auth_host}")
                if getattr(server_cfg, 'custom_mappings', None):
                    for orig, target in server_cfg.custom_mappings.items():
                        domain_lines.append(f"{orig}={target}")

                # 1. Write domain.cfg to assets/
                assets_dir = decoded_dir / "assets"
                assets_dir.mkdir(parents=True, exist_ok=True)
                (assets_dir / "domain.cfg").write_text("\n".join(domain_lines) + "\n", encoding="utf-8")
                logger.detail(f"Created assets/domain.cfg with {len(domain_lines)} mapping(s)")

                # 2. Inject libneki.so into lib/<abi>/
                templates_libs = Path(__file__).parent.parent / "templates" / "libs"
                lib_dir = decoded_dir / "lib"
                if lib_dir.exists():
                    for abi_dir in lib_dir.iterdir():
                        if abi_dir.is_dir():
                            src_so = templates_libs / abi_dir.name / "libneki.so"
                            if src_so.exists():
                                shutil.copy(src_so, abi_dir / "libneki.so")
                                logger.detail(f"Injected libneki.so into lib/{abi_dir.name}/")
                            else:
                                logger.warn(f"Pre-built libneki.so not found for ABI: {abi_dir.name}")

                # 3. Inject NekiHookLoader.smali (Tự động chọn thư mục smali)
                loader_template = Path(__file__).parent.parent / "templates" / "NekiHookLoader.smali"
                if loader_template.exists():
                    target_smali_base = self._get_target_smali_dir(decoded_dir)
                    dest_smali_dir = target_smali_base / "moe" / "low" / "arc" / "custom"
                    dest_smali_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(loader_template, dest_smali_dir / "NekiHookLoader.smali")
                    logger.detail("Injected NekiHookLoader.smali")
                else:
                    logger.warn("NekiHookLoader.smali template not found!")

                # 4. Inject hook trigger into Activity Smali
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.inject_domain_hook_loader()

            # Phase 5: Native Binary Patching (SSL Bypass + Domain Redirection via Assembly & .rodata)
            logger.header("[6/8] Patching Native Binaries (.so)")
            so_files = list(decoded_dir.glob("lib/**/libcocos2dcpp.so"))
            if not so_files:
                logger.warn("No libcocos2dcpp.so binaries found.")
            for so_file in so_files:
                patcher = NativeLibraryPatcher(so_file)
                patcher.patch_ssl_bypass()

            # Phase 6: Java Bytecode SSL Patching
            if self.config.patch_java_ssl:
                logger.header("[7/8] Patching Java Bytecode")
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.patch_ssl_pinning()

            # Phase 7: Rebuild, Align, and Sign
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
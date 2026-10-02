from pathlib import Path
from typing import Optional
import ipaddress
import re
import shutil
import tempfile
from arcaea_patcher.config import PatchConfig
from arcaea_patcher.core.apk_toolchain import ApkToolchain
from arcaea_patcher.core.elf_patcher import NativeLibraryPatcher
from arcaea_patcher.core.manifest_patcher import ManifestAndSecurityPatcher
from arcaea_patcher.core.smali_patcher import SmaliPatcher
from arcaea_patcher.utils.logger import logger


_CONTROL_OR_QUOTE_RE = re.compile(r'[\x00-\x1f\x7f"]')
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_host(value: Optional[str]) -> Optional[str]:
    """Strips control bytes/quotes that would make inet_pton() fail on device."""
    if value is None:
        return None
    cleaned = _CONTROL_OR_QUOTE_RE.sub("", value).strip()
    if cleaned != value:
        logger.warn(f"Sanitised host value {value!r} -> {cleaned!r}")
    return cleaned


def _is_plausible_host(value: Optional[str]) -> bool:
    """Best-effort check that `value` is a hostname, IP or host:port pair."""
    if not value:
        return False
    host = value
    if ":" in value and not value.startswith("["):
        host = value.rsplit(":", 1)[0]
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.match(host))


class PatchPipeline:
    """Coordinates decompilation, patching, and recompilation phases."""

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
        """Merges the baked templates tree into the decoded APK."""
        if not self.templates_dir.is_dir():
            logger.warn(f"Templates directory not found: {self.templates_dir}")
            return 0

        copied = 0
        for source in sorted(self.templates_dir.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(self.templates_dir)
            destination = decoded_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            logger.detail(f"Merged template: {relative.as_posix()}")
            copied += 1
        return copied

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
            logger.header("[1/9] Decompiling APK")
            self.toolchain.decompile(self.config.input_apk, decoded_dir)
            logger.success("APK successfully decoded.")

            # Phase 2: Merge baked templates (native libs + Java classes)
            logger.header("[2/9] Merging Baked Templates")
            merged = self._merge_templates(decoded_dir)
            if merged:
                logger.success(f"Merged {merged} template file(s) into the decoded APK.")
            else:
                logger.warn("No template files merged (run complie.py to bake templates).")

            # Phase 3: Manifest & Network Security Config
            manifest_patcher = ManifestAndSecurityPatcher(decoded_dir)
            if self.config.package_name:
                logger.header("[3/9] Changing Package Name")
                manifest_patcher.change_package_name(self.config.package_name)

            if self.config.inject_nsc:
                logger.header("[4/9] Injecting Network Security Config")
                manifest_patcher.inject_network_security_config()

            # Phase 4: Storage Access Framework provider (manifest entry only;
            # the provider class itself comes from the merged templates)
            if self.config.feature_config.expose_internal_data:
                logger.header("[5/9] Injecting Storage Access Framework Provider")
                manifest_patcher.inject_documents_provider()

            # Phase 5: Dynamic Domain Routing via libneki.so (Native Hook)
            server_cfg = self.config.server
            has_domain_routing = bool(
                server_cfg and (server_cfg.api_host or server_cfg.auth_host or server_cfg.custom_mappings)
            )

            if has_domain_routing:
                logger.header("[6/9] Writing Domain Routing Config (domain.cfg)")

                # Try to import constants; fall back if an error occurs.
                try:
                    from arcaea_patcher.constants import API_DOMAINS, AUTH_DOMAINS
                except ImportError:
                    API_DOMAINS = ["arcapi-v4.lowiro.com", "arcapi-v3.lowiro.com", "arcaea.lowiro.com"]
                    AUTH_DOMAINS = ["auth-v2.lowiro.com", "auth.lowiro.com"]

                api_host = _sanitize_host(self.config.server.api_host)
                auth_host = _sanitize_host(self.config.server.auth_host)
                if api_host and not _is_plausible_host(api_host):
                    logger.warn(f"api_host '{api_host}' does not look like a valid host/IP; redirect may fail")
                if auth_host and not _is_plausible_host(auth_host):
                    logger.warn(f"auth_host '{auth_host}' does not look like a valid host/IP; redirect may fail")

                domain_lines = []
                if api_host:
                    for d in API_DOMAINS:
                        domain_lines.append(f"{d}={api_host}")
                if auth_host:
                    for d in AUTH_DOMAINS:
                        domain_lines.append(f"{d}={auth_host}")
                if getattr(server_cfg, 'custom_mappings', None):
                    for orig, target in server_cfg.custom_mappings.items():
                        domain_lines.append(
                            f"{_sanitize_host(orig)}={_sanitize_host(target)}"
                        )

                # 1. Write domain.cfg to assets/ (force LF so the on-device parser
                #    never sees Windows CRLF line endings).
                assets_dir = decoded_dir / "assets"
                assets_dir.mkdir(parents=True, exist_ok=True)
                cfg_path = assets_dir / "domain.cfg"
                with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write("\n".join(domain_lines) + "\n")
                logger.detail(f"Created assets/domain.cfg with {len(domain_lines)} mapping(s)")

                # 2. Inject the native hook trigger into the Activity smali
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.inject_domain_hook_loader()

            # Phase 6: Native Binary Patching (SSL Bypass + Domain Redirection via Assembly & .rodata)
            logger.header("[7/9] Patching Native Binaries (.so)")
            so_files = list(decoded_dir.glob("lib/**/libcocos2dcpp.so"))
            if not so_files:
                logger.warn("No libcocos2dcpp.so binaries found.")
            for so_file in so_files:
                patcher = NativeLibraryPatcher(so_file)
                patcher.patch_ssl_bypass()

            # Phase 7: Java Bytecode SSL Patching
            if self.config.patch_java_ssl:
                logger.header("[8/9] Patching Java Bytecode")
                smali_patcher = SmaliPatcher(decoded_dir)
                smali_patcher.patch_ssl_pinning()

            # Phase 8: Rebuild, Align, and Sign
            logger.header("[9/9] Rebuilding & Signing APK")
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

from pathlib import Path
import re
from arcaea_patcher.utils.logger import logger


class ManifestAndSecurityPatcher:
    """Manages AndroidManifest.xml and Network Security Configuration modifications."""

    NSC_XML = """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
"""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir
        self.manifest_file = decoded_dir / "AndroidManifest.xml"
        self.apktool_yml = decoded_dir / "apktool.yml"

    def inject_network_security_config(self) -> None:
        """Creates res/xml/network_security_config.xml and binds it in AndroidManifest.xml."""
        xml_dir = self.decoded_dir / "res" / "xml"
        xml_dir.mkdir(parents=True, exist_ok=True)
        (xml_dir / "network_security_config.xml").write_text(self.NSC_XML, encoding="utf-8")
        logger.detail("Created res/xml/network_security_config.xml")

        if not self.manifest_file.is_file():
            logger.warn("AndroidManifest.xml not found; skipping NSC attribute injection")
            return

        text = self.manifest_file.read_text(encoding="utf-8")
        if "android:networkSecurityConfig" not in text:
            text = re.sub(
                r"<application\s+",
                '<application android:networkSecurityConfig="@xml/network_security_config" ',
                text,
                count=1,
            )
            self.manifest_file.write_text(text, encoding="utf-8")
            logger.success("Added networkSecurityConfig attribute to AndroidManifest.xml")
        else:
            logger.detail("AndroidManifest.xml already contains networkSecurityConfig")

    def inject_documents_provider(self) -> None:
        """Injects InternalStorageProvider into AndroidManifest.xml for SAF file access."""
        if not self.manifest_file.is_file():
            logger.warn("AndroidManifest.xml not found; skipping provider injection")
            return

        text = self.manifest_file.read_text(encoding="utf-8")
        if "android.content.action.DOCUMENTS_PROVIDER" in text:
            logger.detail("InternalStorageProvider already present in manifest")
            return

        match = re.search(r'<manifest[^>]*\s+package="([^"]+)"', text)
        if not match:
            logger.warn("Could not determine package name from AndroidManifest.xml")
            return
        pkg = match.group(1)

        provider_xml = f"""
        <provider
            android:name="moe.neki.arc.InternalStorageProvider"
            android:authorities="{pkg}.documents"
            android:exported="true"
            android:grantUriPermissions="true"
            android:permission="android.permission.MANAGE_DOCUMENTS">
            <intent-filter>
                <action android:name="android.content.action.DOCUMENTS_PROVIDER" />
            </intent-filter>
            <grant-uri-permission android:pathPattern=".*" />
        </provider>
"""
        text = text.replace("</application>", f"{provider_xml}    </application>")
        self.manifest_file.write_text(text, encoding="utf-8")
        logger.success("Injected InternalStorageProvider into AndroidManifest.xml")

    def change_package_name(self, new_pkg: str) -> None:
        """Renames package attribute, owned custom permissions, and apktool config."""
        if not self.manifest_file.is_file():
            logger.warn("AndroidManifest.xml not found; cannot rename package")
            return

        text = self.manifest_file.read_text(encoding="utf-8")
        match = re.search(r'<manifest[^>]*\s+package="([^"]+)"', text)
        if not match:
            logger.warn("Could not extract current package name from manifest")
            return

        old_pkg = match.group(1)
        if old_pkg == new_pkg:
            logger.detail(f"Package name is already '{new_pkg}'")
            return

        # Rename app-owned custom permissions to prevent duplicate permission conflicts on install
        owned_perms = sorted({
            name for name in re.findall(r'<(?:uses-)?permission[^>]*android:name="([^"]+)"', text)
            if name == old_pkg or name.startswith(old_pkg + ".")
        })
        for perm in owned_perms:
            logger.detail(f"Renaming permission: {perm} -> {new_pkg}{perm[len(old_pkg):]}")

        text, count = re.subn(
            rf'(?<![A-Za-z0-9_.]){re.escape(old_pkg)}(?=[.": ]|$)',
            lambda _: new_pkg,
            text,
        )
        if count > 0:
            logger.detail(f"Renamed {count} package reference(s)")

        self.manifest_file.write_text(text, encoding="utf-8")
        logger.success(f"Changed package name: {old_pkg} -> {new_pkg}")

        # Update apktool.yml to reflect renamed package
        if self.apktool_yml.is_file():
            yml_text = self.apktool_yml.read_text(encoding="utf-8")
            if "renameManifestPackage:" in yml_text:
                yml_text = re.sub(r"renameManifestPackage:\s*.*", f"renameManifestPackage: {new_pkg}", yml_text)
            else:
                yml_text += f"\nrenameManifestPackage: {new_pkg}\n"
            self.apktool_yml.write_text(yml_text, encoding="utf-8")
            logger.detail(f"Updated apktool.yml renameManifestPackage to {new_pkg}")

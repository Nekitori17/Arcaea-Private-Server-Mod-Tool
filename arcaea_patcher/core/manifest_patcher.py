from pathlib import Path
import re
from arcaea_patcher.utils.logger import logger


class ManifestAndSecurityPatcher:
    """Manages AndroidManifest.xml and Network Security Configuration injections."""

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

    def inject_network_security_config(self) -> None:
        xml_dir = self.decoded_dir / "res" / "xml"
        xml_dir.mkdir(parents=True, exist_ok=True)

        nsc_file = xml_dir / "network_security_config.xml"
        nsc_file.write_text(self.NSC_XML, encoding="utf-8")
        logger.detail("Created res/xml/network_security_config.xml")

        manifest_file = self.decoded_dir / "AndroidManifest.xml"
        if not manifest_file.exists():
            logger.warn("AndroidManifest.xml not found!")
            return

        manifest_text = manifest_file.read_text(encoding="utf-8")
        if "android:networkSecurityConfig" not in manifest_text:
            manifest_text = re.sub(
                r"<application\s+",
                '<application android:networkSecurityConfig="@xml/network_security_config" ',
                manifest_text,
                count=1,
            )
            manifest_file.write_text(manifest_text, encoding="utf-8")
            logger.success("Added networkSecurityConfig attribute to AndroidManifest.xml")
        else:
            logger.detail("Manifest already contains networkSecurityConfig attribute.")

    def inject_documents_provider(self) -> None:
        manifest_file = self.decoded_dir / "AndroidManifest.xml"
        if not manifest_file.exists():
            logger.warn("AndroidManifest.xml not found!")
            return

        manifest_text = manifest_file.read_text(encoding="utf-8")
        
        if "android.content.action.DOCUMENTS_PROVIDER" in manifest_text:
            logger.detail("Manifest already contains DocumentsProvider.")
            return
            
        match = re.search(r'<manifest[^>]*\s+package="([^"]+)"', manifest_text)
        if not match:
            logger.warn("Could not find package attribute in AndroidManifest.xml")
            return
        current_pkg = match.group(1)

        provider_xml = f"""
        <provider
            android:name="moe.neki.arc.InternalStorageProvider"
            android:authorities="{current_pkg}.documents"
            android:exported="true"
            android:grantUriPermissions="true"
            android:permission="android.permission.MANAGE_DOCUMENTS">
            <intent-filter>
                <action android:name="android.content.action.DOCUMENTS_PROVIDER" />
            </intent-filter>
            <!-- Required on Android 14+ (SDK 34+) for persistable URI permissions -->
            <grant-uri-permission android:pathPattern=".*" />
        </provider>
"""
        # Inject just before the closing </application> tag
        manifest_text = manifest_text.replace("</application>", f"{provider_xml}    </application>")
        manifest_file.write_text(manifest_text, encoding="utf-8")
        logger.success("Injected InternalStorageProvider into AndroidManifest.xml")

    def change_package_name(self, new_package_name: str) -> None:
        manifest_file = self.decoded_dir / "AndroidManifest.xml"
        if not manifest_file.exists():
            logger.warn("AndroidManifest.xml not found!")
            return

        manifest_text = manifest_file.read_text(encoding="utf-8")

        # Find original package name
        match = re.search(r'<manifest[^>]*\s+package="([^"]+)"', manifest_text)
        if not match:
            logger.warn("Could not find package attribute in AndroidManifest.xml")
            return

        old_package_name = match.group(1)
        if old_package_name == new_package_name:
            logger.detail(f"Package name is already {new_package_name}")
            return

        # App-owned permissions (e.g. "<pkg>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION")
        # must follow the new package too, otherwise installing this APK next to the
        # original one fails with INSTALL_FAILED_DUPLICATE_PERMISSION.
        owned_permissions = sorted(
            {
                name
                for name in re.findall(
                    r'<(?:uses-)?permission(?:-sdk-23)?[^>]*android:name="([^"]+)"',
                    manifest_text,
                )
                if name == old_package_name or name.startswith(old_package_name + ".")
            }
        )
        for permission in owned_permissions:
            logger.detail(
                "Renaming permission: "
                f"{permission} -> {new_package_name}{permission[len(old_package_name):]}"
            )

        # Rename the package attribute plus every identifier derived from it:
        # provider authorities, android:permission / android:process and the
        # permission names collected above. Only whole, dot-bounded occurrences are
        # replaced, so unrelated strings such as "low.moe.AppActivity" stay intact.
        manifest_text, renamed_count = re.subn(
            rf'(?<![A-Za-z0-9_.]){re.escape(old_package_name)}(?=[.": ]|$)',
            lambda _match: new_package_name,
            manifest_text,
        )
        if renamed_count == 0:
            logger.warn("No package references were renamed (unexpected).")
        else:
            logger.detail(f"Renamed {renamed_count} package reference(s), permissions included")

        manifest_file.write_text(manifest_text, encoding="utf-8")
        logger.success(f"Changed package name from {old_package_name} to {new_package_name} in AndroidManifest.xml")

        # Also update apktool.yml so Apktool builds the APK correctly
        apktool_yml = self.decoded_dir / "apktool.yml"
        if apktool_yml.exists():
            yml_text = apktool_yml.read_text(encoding="utf-8")
            if "renameManifestPackage:" in yml_text:
                yml_text = re.sub(r"renameManifestPackage:\s*.*", f"renameManifestPackage: {new_package_name}", yml_text)
            else:
                yml_text += f"\nrenameManifestPackage: {new_package_name}\n"
            apktool_yml.write_text(yml_text, encoding="utf-8")
            logger.detail(f"Updated apktool.yml renameManifestPackage to {new_package_name}")

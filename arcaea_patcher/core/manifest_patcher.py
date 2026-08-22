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
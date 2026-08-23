from pathlib import Path
import re
from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java SSL verification bypass."""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir

    def patch_ssl_pinning(self) -> None:
        smali_files = list(self.decoded_dir.glob("**/Cocos2dxHttpURLConnection.smali"))
        if not smali_files:
            logger.warn("Cocos2dxHttpURLConnection.smali not found. Skipping Java SSL patch.")
            return

        for path in smali_files:
            content = path.read_text(encoding="utf-8")
            method_pattern = re.compile(
                r"(\.method\s+[^\n]*verifySSLPins\([^\n]*\)([VZ])\n)(.*?)(\.end method)",
                re.DOTALL,
            )

            match = method_pattern.search(content)
            if match:
                header, return_type, _, footer = match.groups()
                if return_type == "Z":
                    replacement = f"{header}    .locals 1\n    const/4 v0, 0x1\n    return v0\n{footer}"
                else:
                    replacement = f"{header}    .locals 0\n    return-void\n{footer}"

                content = method_pattern.sub(replacement, content, count=1)
                path.write_text(content, encoding="utf-8")
                logger.success(f"Patched Java verifySSLPins in {path.relative_to(self.decoded_dir)}")
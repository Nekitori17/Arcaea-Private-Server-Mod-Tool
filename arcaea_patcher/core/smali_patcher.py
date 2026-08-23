from pathlib import Path
import re
from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java SSL verification bypass."""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir

    def _replace_method_body(
        self, content: str, method_name: str
    ) -> tuple[str, bool]:
        """Replace the body of a smali method with a trivial return.

        For boolean (Z) return types the replacement returns ``1`` (true).
        For void (V) methods it emits ``return-void``.
        """
        method_pattern = re.compile(
            rf"(\.method\s+[^\n]*{re.escape(method_name)}\([^\n]*\)([VZ])\n)"
            r"(.*?)"
            r"(\.end method)",
            re.DOTALL,
        )

        match = method_pattern.search(content)
        if not match:
            return content, False

        header, return_type, _, footer = match.groups()
        if return_type == "Z":
            replacement = (
                f"{header}    .locals 1\n    const/4 v0, 0x1\n    return v0\n{footer}"
            )
        else:
            replacement = f"{header}    .locals 0\n    return-void\n{footer}"

        return method_pattern.sub(replacement, content, count=1), True

    def patch_ssl_pinning(self) -> None:
        smali_files = list(self.decoded_dir.glob("**/Cocos2dxHttpURLConnection.smali"))
        if not smali_files:
            logger.warn("Cocos2dxHttpURLConnection.smali not found. Skipping Java SSL patch.")
            return

        target_methods = ["setVerifySSL", "verifySSLPins"]

        for path in smali_files:
            content = path.read_text(encoding="utf-8")
            changed = False

            for method_name in target_methods:
                content, patched = self._replace_method_body(content, method_name)
                if patched:
                    logger.success(
                        f"Patched Java {method_name} in {path.relative_to(self.decoded_dir)}"
                    )
                    changed = True

            if changed:
                path.write_text(content, encoding="utf-8")
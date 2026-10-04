from pathlib import Path
import re
from typing import List, Tuple

from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java-level SSL bypass and native hook loading."""

    _NEUTRAL_BODIES = {
        "V": "    .locals 0\n    return-void\n",
        "Z": "    .locals 1\n    const/4 v0, 0x1\n    return v0\n",
        "I": "    .locals 1\n    const/4 v0, 0x1\n    return v0\n",
    }

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir

    def _replace_method_body(self, content: str, method_name: str) -> Tuple[str, int, str]:
        """Replaces method body with neutral return instruction."""
        pattern = re.compile(
            rf"(\.method\s+[^\n]*\b{re.escape(method_name)}\([^\n]*\)([^\s\r\n]+)\r?\n)"
            r"(.*?)"
            r"(\.end method)",
            re.DOTALL,
        )

        patched = 0
        skipped: List[str] = []

        def _replace(match: re.Match) -> str:
            nonlocal patched
            header, ret_type, _body, footer = match.groups()
            if re.search(r"\b(?:native|abstract)\b", header):
                skipped.append("native/abstract method")
                return match.group(0)
            replacement = self._NEUTRAL_BODIES.get(ret_type)
            if replacement is None:
                skipped.append(f"unsupported return type '{ret_type}'")
                return match.group(0)
            patched += 1
            return f"{header}{replacement}{footer}"

        new_content = pattern.sub(_replace, content)
        return new_content, patched, "; ".join(sorted(set(skipped)))

    def patch_ssl_pinning(self) -> None:
        """Neutralizes Java verification in Cocos2dxHttpURLConnection.smali."""
        smali_files = list(self.decoded_dir.glob("**/Cocos2dxHttpURLConnection.smali"))
        if not smali_files:
            logger.warn("Cocos2dxHttpURLConnection.smali not found; skipping Java SSL patch")
            return

        target_methods = ["setVerifySSL", "verifySSLPins"]
        for path in smali_files:
            content = path.read_text(encoding="utf-8")
            changed = False
            rel = path.relative_to(self.decoded_dir)

            for method in target_methods:
                content, patched, note = self._replace_method_body(content, method)
                if patched:
                    logger.success(f"Patched Java {method} ({patched} overload(s)) in {rel}")
                    if note:
                        logger.warn(f"Untouched in {method}: {note}")
                    changed = True
                else:
                    logger.warn(f"Could not patch {method} in {rel}: {note or 'not found'}")

            if changed:
                path.write_text(content, encoding="utf-8")

    def inject_domain_hook_loader(self) -> bool:
        """Injects NekiLoader.init() into primary Activity onCreate()."""
        hook_call = "    invoke-static/range {p0 .. p0}, Lmoe/neki/arc/NekiLoader;->init(Landroid/content/Context;)V\n"
        candidates = ["**/AppActivity.smali", "**/MainActivity.smali", "**/Cocos2dxActivity.smali"]

        for pattern in candidates:
            for path in self.decoded_dir.glob(pattern):
                content = path.read_text(encoding="utf-8")
                if "Lmoe/neki/arc/NekiLoader;->init" in content:
                    logger.detail(f"NekiLoader already present in {path.name}")
                    return True

                method_match = re.search(
                    r"(\.method\s+[^\n]*onCreate\(Landroid/os/Bundle;\)V\r?\n)(.*?)(\.end method)",
                    content,
                    re.DOTALL,
                )
                if not method_match:
                    continue

                header, body, footer = method_match.groups()
                super_match = re.search(
                    r"(invoke-super(?:/range)?\s+\{[^\}]+\},\s+L[^\n]+;->onCreate\(Landroid/os/Bundle;\)V\r?\n)",
                    body,
                )

                if super_match:
                    new_body = body.replace(super_match.group(1), super_match.group(1) + hook_call, 1)
                else:
                    reg_match = re.search(r"(\s*\.(?:locals|registers)\s+\d+\r?\n)", body)
                    if reg_match:
                        new_body = body.replace(reg_match.group(1), reg_match.group(1) + hook_call, 1)
                    else:
                        new_body = hook_call + body

                content = content.replace(method_match.group(0), f"{header}{new_body}{footer}", 1)
                path.write_text(content, encoding="utf-8")
                logger.success(f"Injected NekiLoader into {path.relative_to(self.decoded_dir)}")
                return True

        logger.warn("No suitable Activity found to inject NekiLoader")
        return False
from pathlib import Path
import re
from typing import Dict, List, Tuple
from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java SSL verification bypass and domain redirection."""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir

    def patch_ssl_pinning(self) -> None:
        smali_files = list(self.decoded_dir.glob("**/Cocos2dxHttpURLConnection.smali"))
        if not smali_files:
            logger.warn("Cocos2dxHttpURLConnection.smali not found. Skipping Java SSL patch.")
            return

        for path in smali_files:
            content = path.read_text(encoding="utf-8")
            # Match verifySSLPins method with either void (V) or boolean (Z) return
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

    def inject_domain_replacement(self, replacements: List[Tuple[str, str]]) -> None:
        if not replacements:
            return

        smali_files = list(self.decoded_dir.glob("**/Cocos2dxHttpURLConnection.smali"))
        if not smali_files:
            return

        injection_block = ["\n    # [INJECTED: DOMAIN REPLACEMENT]"]
        for old_host, new_host in replacements:
            injection_block.append(f'    const-string v0, "{old_host}"')
            injection_block.append(f'    const-string v1, "{new_host}"')
            injection_block.append(
                "    invoke-virtual {p0, v0, v1}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;"
            )
            injection_block.append("    move-result-object p0")
        injection_block.append("    # [END INJECTED]\n")
        inject_code = "\n".join(injection_block)

        for path in smali_files:
            content = path.read_text(encoding="utf-8")
            method_regex = re.compile(
                r"(\.method\s+static\s+createHttpURLConnection\(Ljava/lang/String;\)Ljava/net/HttpURLConnection;\s*\n\s*\.locals\s+)(\d+)"
            )

            def _replacer(m: re.Match) -> str:
                prefix = m.group(1)
                count = max(int(m.group(2)), 2)
                return f"{prefix}{count}\n{inject_code}"

            new_content, count = method_regex.subn(_replacer, content, count=1)
            if count > 0:
                path.write_text(new_content, encoding="utf-8")
                logger.success(f"Injected host redirection into {path.relative_to(self.decoded_dir)}")
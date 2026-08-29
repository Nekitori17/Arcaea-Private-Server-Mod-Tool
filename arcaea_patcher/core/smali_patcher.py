import re
from pathlib import Path
from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java SSL verification bypass and native hook injection."""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir

    def _replace_method_body(
        self, content: str, method_name: str
    ) -> tuple[str, bool]:
        # Supports both Windows (\r\n) and Unix (\n) line endings
        method_pattern = re.compile(
            rf"(\.method\s+[^\n]*{re.escape(method_name)}\([^\n]*\)([VZ])\r?\n)"
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

        # Using direct string replacement to avoid regex escape sequence issues
        patched_content = content.replace(match.group(0), replacement, 1)
        return patched_content, True

    def patch_ssl_pinning(self) -> None:
        """Bypasses Java-level SSL pinning inside Cocos2dxHttpURLConnection."""
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

    def inject_domain_hook_loader(self) -> bool:
        # Prioritize leaf activities over parent base classes
        candidate_patterns = [
            "**/AppActivity.smali",
            "**/MainActivity.smali",
            "**/Cocos2dxActivity.smali",
        ]

        hook_call = "    invoke-static/range {p0 .. p0}, Lmoe/low/arc/custom/NekiHookLoader;->init(Landroid/content/Context;)V\n"

        for pattern in candidate_patterns:
            files = list(self.decoded_dir.glob(pattern))
            for path in files:
                content = path.read_text(encoding="utf-8")

                # Check if hook is already injected
                if "Lmoe/low/arc/custom/NekiHookLoader;->init" in content:
                    logger.detail(f"NekiHookLoader already present in {path.name}")
                    return True

                # Locate the onCreate method block
                method_match = re.search(
                    r"(\.method\s+[^\n]*onCreate\(Landroid/os/Bundle;\)V\r?\n)(.*?)(\.end method)",
                    content,
                    re.DOTALL,
                )
                if not method_match:
                    continue

                header, body, footer = method_match.groups()

                # Find super.onCreate(...) call (supports standard and /range variants)
                super_match = re.search(
                    r"(invoke-super(?:/range)?\s+\{[^\}]+\},\s+L[^\n]+;->onCreate\(Landroid/os/Bundle;\)V\r?\n)",
                    body,
                )

                if super_match:
                    # Insert hook call immediately after super.onCreate()
                    new_body = body.replace(super_match.group(1), super_match.group(1) + hook_call, 1)
                else:
                    # Fallback: insert after .locals or .registers declaration
                    registers_match = re.search(r"(\s*\.(?:locals|registers)\s+\d+\r?\n)", body)
                    if registers_match:
                        new_body = body.replace(registers_match.group(1), registers_match.group(1) + hook_call, 1)
                    else:
                        new_body = hook_call + body

                new_method = f"{header}{new_body}{footer}"
                content = content.replace(method_match.group(0), new_method, 1)

                path.write_text(content, encoding="utf-8")
                logger.success(f"Injected NekiHookLoader into {path.relative_to(self.decoded_dir)}")
                
                # Stop after injecting into the primary entry activity
                return True

        logger.warn("No suitable Activity found to inject NekiHookLoader!")
        return False
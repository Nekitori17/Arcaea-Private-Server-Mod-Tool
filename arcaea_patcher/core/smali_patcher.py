from pathlib import Path
import re
from arcaea_patcher.utils.logger import logger


class SmaliPatcher:
    """Patches Smali bytecode for Java SSL verification bypass and dynamic hooks."""

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


    def inject_domain_hook_loader(self) -> bool:
        """Injects NekiHookLoader.init(this) into the main Activity's onCreate method."""
        target_patterns = ["**/Cocos2dxActivity.smali", "**/AppActivity.smali"]
        injected = False

        for pattern in target_patterns:
            files = list(self.decoded_dir.glob(pattern))
            for path in files:
                content = path.read_text(encoding="utf-8")
                if "Lmoe/low/arc/custom/NekiHookLoader;->init" in content:
                    logger.detail(f"NekiHookLoader already injected in {path.name}")
                    injected = True
                    continue

                # Locate the code block for the onCreate function.
                method_match = re.search(
                    r"(\.method\s+[^\n]*onCreate\(Landroid/os/Bundle;\)V\n)(.*?)(\.end method)",
                    content,
                    re.DOTALL,
                )
                if not method_match:
                    continue

                header, body, footer = method_match.groups()

                # Regex Update: Supports both `invoke-super` and `invoke-super/range`
                super_match = re.search(
                    r"(invoke-super(?:/range)?\s+\{[^\}]+\},\s+L[^\n]+;->onCreate\(Landroid/os/Bundle;\)V\n)",
                    body,
                )

                # Dalvik logic update: Use invoke-static/range to avoid the 16-bit register limit error (v0–v15).
                # When the Smali file is very long, the parameter variable p0 may exceed v15.
                hook_call = "    invoke-static/range {p0 .. p0}, Lmoe/low/arc/custom/NekiHookLoader;->init(Landroid/content/Context;)V\n"

                if super_match:
                    # Insert immediately after the super.onCreate() call
                    new_body = body.replace(super_match.group(1), super_match.group(1) + hook_call, 1)
                else:
                    # If the super function is not found, insert immediately after the .locals declaration.
                    locals_match = re.search(r"(\s*\.locals\s+\d+\n)", body)
                    if locals_match:
                        new_body = body.replace(locals_match.group(1), locals_match.group(1) + hook_call, 1)
                    else:
                        new_body = hook_call + body

                new_method = f"{header}{new_body}{footer}"
                content = content.replace(method_match.group(0), new_method, 1)
                
                path.write_text(content, encoding="utf-8")
                logger.success(f"Injected NekiHookLoader into {path.relative_to(self.decoded_dir)}")
                injected = True

        return injected
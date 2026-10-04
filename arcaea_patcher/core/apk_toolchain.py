import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from arcaea_patcher.config import SigningConfig
from arcaea_patcher.utils.logger import logger


class ToolchainError(RuntimeError):
    """Raised when an external toolchain binary or JAR fails or is missing."""
    pass


class ApkToolchain:
    """Discovers and executes Android build-tools, Apktool, and signing utilities."""

    def __init__(
        self,
        lib_dir: Optional[Path] = None,
        build_tools_dir: Optional[Path] = None,
    ):
        self.lib_dir = lib_dir or Path("lib")
        self.custom_build_tools_dir = build_tools_dir or Path("build-tools")

    @staticmethod
    def _version_key(path: Path) -> Tuple[int, ...]:
        """Extracts integer version tuple from directory name."""
        nums = re.findall(r"\d+", path.name)
        return tuple(map(int, nums)) if nums else (0,)

    def _discover_build_tools_dirs(self) -> List[Path]:
        """Finds potential Android SDK build-tools directories ordered newest first."""
        candidates: List[Path] = []

        if self.custom_build_tools_dir.is_dir():
            candidates.append(self.custom_build_tools_dir)

        for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            val = os.getenv(var)
            if val:
                bt = Path(val) / "build-tools"
                if bt.is_dir():
                    candidates.append(bt)

        home = Path.home()
        if sys.platform == "win32":
            local_appdata = os.getenv("LOCALAPPDATA")
            if local_appdata:
                candidates.append(Path(local_appdata) / "Android" / "Sdk" / "build-tools")
        elif sys.platform == "darwin":
            candidates.append(home / "Library" / "Android" / "sdk" / "build-tools")
        else:
            candidates.append(home / "Android" / "Sdk" / "build-tools")
            candidates.append(Path("/usr/lib/android-sdk/build-tools"))

        versioned: List[Path] = []
        for parent in candidates:
            if not parent.is_dir():
                continue
            for item in parent.iterdir():
                if item.is_dir():
                    versioned.append(item)
            versioned.append(parent)

        return sorted(versioned, key=self._version_key, reverse=True)

    def _find_binary_in_build_tools(self, name: str) -> Optional[Path]:
        """Searches for tool binary across discovered build-tools paths."""
        suffixes = [".exe", ".bat", ".cmd", ""] if sys.platform == "win32" else [""]
        for bt_dir in self._discover_build_tools_dirs():
            for sfx in suffixes:
                candidate = bt_dir / f"{name}{sfx}"
                if candidate.is_file():
                    return candidate
        return None

    def _resolve_zipalign(self) -> List[str]:
        found = self._find_binary_in_build_tools("zipalign")
        if found:
            logger.detail(f"Found zipalign at: {found}")
            return [str(found)]
        which = shutil.which("zipalign")
        if which:
            return [which]
        raise ToolchainError("zipalign not found. Please install Android SDK build-tools or set ANDROID_HOME.")

    def _resolve_apksigner(self) -> List[str]:
        for bt_dir in self._discover_build_tools_dirs():
            jar = bt_dir / "lib" / "apksigner.jar"
            if jar.is_file():
                logger.detail(f"Found apksigner.jar at: {jar}")
                return ["java", "-jar", str(jar)]

        local_jar = self.lib_dir / "apksigner.jar"
        if local_jar.is_file():
            return ["java", "-jar", str(local_jar)]

        found = self._find_binary_in_build_tools("apksigner")
        if found:
            logger.detail(f"Found apksigner script at: {found}")
            return [str(found)]

        which = shutil.which("apksigner")
        if which:
            return [which]

        raise ToolchainError("apksigner not found. Place apksigner.jar in lib/ or configure Android build-tools.")

    def _resolve_apktool(self) -> List[str]:
        local_jar = self.lib_dir / "apktool.jar"
        if local_jar.is_file():
            return ["java", "-jar", str(local_jar)]
        which = shutil.which("apktool")
        if which:
            return [which]
        raise ToolchainError("apktool not found. Place apktool.jar in lib/ or add it to PATH.")

    def run_cmd(self, cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Executes a command and raises ToolchainError on non-zero exit."""
        # Wrap Windows batch scripts with cmd.exe /c
        if sys.platform == "win32" and cmd and Path(cmd[0]).suffix.lower() in (".bat", ".cmd"):
            cmd = ["cmd.exe", "/c"] + cmd

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        if res.returncode != 0:
            err_snippet = res.stderr.strip() or res.stdout.strip()
            logger.error(f"Command failed ({res.returncode}): {' '.join(cmd[:4])}")
            if err_snippet:
                logger.detail(f"Error output: {err_snippet[:400]}")
            raise ToolchainError(f"Toolchain execution failed with exit code {res.returncode}")
        return res

    def decompile(self, input_apk: Path, output_dir: Path) -> None:
        """Decompiles APK to output_dir using Apktool."""
        cmd = self._resolve_apktool() + ["d", str(input_apk), "-o", str(output_dir), "-f"]
        self.run_cmd(cmd)

    def build(self, decoded_dir: Path, output_apk: Path) -> None:
        """Rebuilds APK from decoded_dir using Apktool."""
        cmd = self._resolve_apktool() + ["b", str(decoded_dir), "-o", str(output_apk), "-f"]
        self.run_cmd(cmd)

    def zipalign(self, unaligned_apk: Path, aligned_apk: Path) -> None:
        """Aligns 4-byte boundaries on unaligned_apk."""
        cmd = self._resolve_zipalign() + ["-f", "4", str(unaligned_apk), str(aligned_apk)]
        self.run_cmd(cmd)

    def ensure_keystore(self, signing_cfg: SigningConfig) -> None:
        """Generates debug keystore if not already present."""
        if signing_cfg.keystore_path.is_file():
            return
        logger.info(f"Generating debug keystore at {signing_cfg.keystore_path}...")
        keytool = shutil.which("keytool") or "keytool"
        cmd = [
            keytool,
            "-genkey",
            "-v",
            "-keystore",
            str(signing_cfg.keystore_path),
            "-storepass",
            signing_cfg.keystore_password,
            "-alias",
            signing_cfg.alias,
            "-keypass",
            signing_cfg.key_password,
            "-keyalg",
            "RSA",
            "-keysize",
            "2048",
            "-validity",
            "10000",
            "-dname",
            "CN=Android Debug,O=Android,C=US",
        ]
        self.run_cmd(cmd)

    def sign(self, apk_path: Path, signing_cfg: SigningConfig) -> None:
        """Signs APK using apksigner with specified or auto-generated keystore."""
        self.ensure_keystore(signing_cfg)
        cmd = self._resolve_apksigner() + [
            "sign",
            "--ks",
            str(signing_cfg.keystore_path),
            "--ks-key-alias",
            signing_cfg.alias,
            "--ks-pass",
            f"pass:{signing_cfg.keystore_password}",
            "--key-pass",
            f"pass:{signing_cfg.key_password}",
            str(apk_path),
        ]
        self.run_cmd(cmd)
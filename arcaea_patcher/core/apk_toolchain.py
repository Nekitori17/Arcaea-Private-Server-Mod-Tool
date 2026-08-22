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
    """Raised when an external toolchain dependency fails or is missing."""
    pass


class ApkToolchain:
    """Manages discovery and execution of Android toolchain binaries and JARs."""

    def __init__(
        self,
        lib_dir: Optional[Path] = None,
        build_tools_dir: Optional[Path] = None,
    ):
        self.lib_dir = lib_dir or Path("lib")
        self.custom_build_tools_dir = build_tools_dir or Path("build-tools")
        self._cached_build_tools_path: Optional[Path] = None

    # --- Tool Discovery & Resolution ---

    @staticmethod
    def _version_key(dir_path: Path) -> Tuple[int, ...]:
        """Extract numeric version components from directory names (e.g., '34.0.0' -> (34, 0, 0))."""
        numbers = re.findall(r"\d+", dir_path.name)
        return tuple(map(int, numbers)) if numbers else (0,)

    def _discover_build_tools_dirs(self) -> List[Path]:
        """Collect potential Android SDK build-tools parent directories."""
        candidate_parents: List[Path] = []

        # 1. Custom or local build-tools directory
        if self.custom_build_tools_dir.exists():
            candidate_parents.append(self.custom_build_tools_dir)

        # 2. Android SDK environment variables
        for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            sdk_env = os.getenv(env_var)
            if sdk_env:
                bt_path = Path(sdk_env) / "build-tools"
                if bt_path.exists():
                    candidate_parents.append(bt_path)

        # 3. Default OS SDK locations
        home = Path.home()
        if sys.platform == "win32":
            local_appdata = os.getenv("LOCALAPPDATA")
            if local_appdata:
                candidate_parents.append(Path(local_appdata) / "Android" / "Sdk" / "build-tools")
        elif sys.platform == "darwin":
            candidate_parents.append(home / "Library" / "Android" / "sdk" / "build-tools")
        else:  # Linux / Unix
            candidate_parents.append(home / "Android" / "Sdk" / "build-tools")
            candidate_parents.append(Path("/usr/lib/android-sdk/build-tools"))

        # Discover version subdirectories
        versioned_dirs: List[Path] = []
        for parent in candidate_parents:
            if not parent.exists():
                continue
            for item in parent.iterdir():
                if item.is_dir():
                    versioned_dirs.append(item)
            # Also allow the parent directory itself in case it's a flat structure
            versioned_dirs.append(parent)

        # Sort descending by parsed version so the newest build-tools is preferred
        return sorted(versioned_dirs, key=self._version_key, reverse=True)

    def _find_in_build_tools(self, tool_name: str) -> Optional[Path]:
        """Search for a binary across all discovered build-tools folders."""
        exe_suffix = ".exe" if sys.platform == "win32" else ""
        bat_suffix = ".bat" if sys.platform == "win32" else ""

        for bt_dir in self._discover_build_tools_dirs():
            # Check for direct executable
            candidates = [
                bt_dir / f"{tool_name}{exe_suffix}",
                bt_dir / f"{tool_name}{bat_suffix}",
                bt_dir / tool_name,
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
        return None

    def _resolve_zipalign(self) -> List[str]:
        """Resolve zipalign binary from build-tools or PATH."""
        # 1. Search in discovered build-tools
        zipalign_path = self._find_in_build_tools("zipalign")
        if zipalign_path:
            logger.detail(f"Found zipalign at: {zipalign_path}")
            return [str(zipalign_path)]

        # 2. Search in system PATH
        in_path = shutil.which("zipalign")
        if in_path:
            return [in_path]

        raise ToolchainError(
            "Could not find 'zipalign'. Please ensure Android build-tools is installed, "
            "set ANDROID_HOME, or add zipalign to your system PATH."
        )

    def _resolve_apksigner(self) -> List[str]:
        """Resolve apksigner via JAR, wrapper script, or system PATH."""
        # 1. Look for apksigner.jar inside build-tools/<version>/lib/ or local lib/
        for bt_dir in self._discover_build_tools_dirs():
            jar_candidate = bt_dir / "lib" / "apksigner.jar"
            if jar_candidate.is_file():
                logger.detail(f"Found apksigner.jar at: {jar_candidate}")
                return ["java", "-jar", str(jar_candidate)]

        local_jar = self.lib_dir / "apksigner.jar"
        if local_jar.is_file():
            return ["java", "-jar", str(local_jar)]

        # 2. Look for apksigner executable / batch script in build-tools
        apksigner_bin = self._find_in_build_tools("apksigner")
        if apksigner_bin:
            logger.detail(f"Found apksigner script at: {apksigner_bin}")
            return [str(apksigner_bin)]

        # 3. Look in system PATH
        in_path = shutil.which("apksigner")
        if in_path:
            return [in_path]

        raise ToolchainError(
            "Could not find 'apksigner'. Please ensure Android build-tools is installed, "
            "set ANDROID_HOME, or place apksigner.jar in lib/."
        )

    def _resolve_apktool(self) -> List[str]:
        """Resolve apktool via lib/apktool.jar or system PATH."""
        local_jar = self.lib_dir / "apktool.jar"
        if local_jar.is_file():
            return ["java", "-jar", str(local_jar)]

        in_path = shutil.which("apktool")
        if in_path:
            return [in_path]

        raise ToolchainError("Could not find 'apktool'. Please place apktool.jar in lib/ or add it to PATH.")

    # --- Command Runner ---

    def run_cmd(self, cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        if res.returncode != 0:
            logger.error(f"Execution failed: {' '.join(cmd)}")
            if res.stderr:
                logger.detail(f"stderr: {res.stderr[:500]}")
            raise ToolchainError(f"Command exited with return code {res.returncode}")
        return res

    # --- High-Level Operations ---

    def decompile(self, input_apk: Path, output_dir: Path) -> None:
        cmd = self._resolve_apktool()
        cmd.extend(["d", str(input_apk), "-o", str(output_dir), "-f"])
        self.run_cmd(cmd)

    def build(self, decoded_dir: Path, output_apk: Path) -> None:
        cmd = self._resolve_apktool()
        cmd.extend(["b", str(decoded_dir), "-o", str(output_apk), "-f"])
        self.run_cmd(cmd)

    def zipalign(self, unaligned_apk: Path, aligned_apk: Path) -> None:
        cmd = self._resolve_zipalign()
        cmd.extend(["-f", "4", str(unaligned_apk), str(aligned_apk)])
        self.run_cmd(cmd)

    def sign(self, apk_path: Path, signing_cfg: SigningConfig) -> None:
        # Generate a debug keystore if not already existing
        if not signing_cfg.keystore_path.exists():
            logger.info(f"Generating debug keystore at {signing_cfg.keystore_path}...")
            keytool_bin = shutil.which("keytool") or "keytool"
            keytool_cmd = [
                keytool_bin,
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
            self.run_cmd(keytool_cmd)

        cmd = self._resolve_apksigner()
        cmd.extend([
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
        ])
        self.run_cmd(cmd)
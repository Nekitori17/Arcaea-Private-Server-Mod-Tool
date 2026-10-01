#!/usr/bin/env python3
"""Bake the native and java sources of this project into ``arcaea_patcher/templates``.

The script auto-detects the Android SDK (ANDROID_HOME / ANDROID_SDK_ROOT / default
install locations) and then performs two independent builds:

1. ``arcaea_patcher/native`` is compiled with ``ndk-build`` and every produced
   ``libneki.so`` is copied to ``arcaea_patcher/templates/lib/<abi>/``.
2. ``arcaea_patcher/java`` is compiled (javac -> d8 -> baksmali) and the generated
   smali files are written to
   ``arcaea_patcher/templates/smali_classes3/moe/neki/arc/``.

The resulting ``templates`` folder mirrors the layout of a decoded (apktool) APK,
so it can be copied directly into the decompiled APK folder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
NATIVE_DIR = ROOT_DIR / "arcaea_patcher" / "native"
JAVA_DIR = ROOT_DIR / "arcaea_patcher" / "java"
TEMPLATES_DIR = ROOT_DIR / "arcaea_patcher" / "templates"
LOCAL_LIB_DIR = ROOT_DIR / "lib"
LOCAL_BUILD_TOOLS_DIR = ROOT_DIR / "build-tools"

MIN_API = 21
JAVA_SOURCE_LEVEL = "8"
BAKSMALI_MAIN_CLASS = "com.android.tools.smali.baksmali.Main"

# Jars required to run the baksmali CLI. They ship inside the Android SDK command
# line tools (``cmdline-tools/<ver>/lib/external/...``), so nothing is downloaded.
BAKSMALI_ARTIFACTS = (
    "smali-baksmali",
    "baksmali",
    "smali-dexlib2",
    "smali-util",
    "guava",
    "jcommander",
    "failureaccess",
    "jsr305",
    "listenablefuture",
)


def info(message: str) -> None:
    print(f"[*] {message}")


def success(message: str) -> None:
    print(f"[+] {message}")


def warn(message: str) -> None:
    print(f"[!] {message}")


def die(message: str) -> None:
    print(f"[-] {message}")
    sys.exit(1)


def version_key(path: Path) -> tuple[int, ...]:
    """Extract the numeric components of a folder name (e.g. ``34.0.0`` -> (34, 0, 0))."""
    numbers = re.findall(r"\d+", path.name)
    return tuple(int(number) for number in numbers) if numbers else (0,)


def artifact_version(name: str, prefix: str) -> tuple[int, ...]:
    """Extract the version of a jar file name for a given artifact prefix."""
    numbers = re.findall(r"\d+", name[len(prefix):])
    return tuple(int(number) for number in numbers) if numbers else (0,)


def as_command(path: Path) -> list[str]:
    """Return the argv prefix used to execute a tool (batch files need cmd.exe)."""
    if os.name == "nt" and path.suffix.lower() in (".bat", ".cmd"):
        return ["cmd.exe", "/c", str(path)]
    return [str(path)]


def run(argv: list[str], cwd: Path | None = None, label: str | None = None) -> None:
    """Run a tool, streaming its output, and abort the script when it fails."""
    display = " ".join(argv)
    if len(display) > 300:
        display = display[:300] + " ..."
    info(f"{label or 'run'}: {display}")
    result = subprocess.run(argv, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        die(f"{label or argv[0]} failed with exit code {result.returncode}")


def find_android_sdk() -> Path:
    """Locate the Android SDK through the environment or the default OS locations."""
    candidates: list[Path] = []
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value))

    home = Path.home()
    if os.name == "nt":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / "Android" / "Sdk")
    elif sys.platform == "darwin":
        candidates.append(home / "Library" / "Android" / "sdk")
    else:
        candidates.append(home / "Android" / "Sdk")
        candidates.append(Path("/usr/lib/android-sdk"))

    for candidate in candidates:
        if candidate.is_dir():
            info(f"Android SDK : {candidate}")
            return candidate

    die("Android SDK not found. Set ANDROID_HOME (or ANDROID_SDK_ROOT) to your SDK folder.")
    return Path("")


def find_ndk_build(sdk: Path) -> Path:
    """Locate ndk-build: ANDROID_NDK_HOME/ROOT, then <sdk>/ndk/<newest>, then ndk-bundle."""
    executable = "ndk-build.cmd" if os.name == "nt" else "ndk-build"
    roots: list[Path] = []

    for variable in ("ANDROID_NDK_HOME", "ANDROID_NDK_ROOT"):
        value = os.getenv(variable)
        if value:
            roots.append(Path(value))

    ndk_dir = sdk / "ndk"
    if ndk_dir.is_dir():
        versions = sorted((item for item in ndk_dir.iterdir() if item.is_dir()), key=version_key, reverse=True)
        roots.extend(versions)

    legacy_bundle = sdk / "ndk-bundle"
    if legacy_bundle.is_dir():
        roots.append(legacy_bundle)

    for root in roots:
        candidate = root / executable
        if candidate.is_file():
            info(f"NDK         : {root}")
            return candidate

    die(f"{executable} not found. Install an NDK (SDK manager) or set ANDROID_NDK_HOME.")
    return Path("")


def find_host_tool(sdk: Path, tool: str) -> Path:
    """Locate an SDK build tool (newest SDK build-tools, then the local build-tools folder)."""
    names = [f"{tool}.exe", f"{tool}.bat", f"{tool}.cmd", tool] if os.name == "nt" else [tool]
    parents: list[Path] = []

    sdk_build_tools = sdk / "build-tools"
    if sdk_build_tools.is_dir():
        versions = sorted((item for item in sdk_build_tools.iterdir() if item.is_dir()), key=version_key, reverse=True)
        parents.extend(versions)
        parents.append(sdk_build_tools)

    if LOCAL_BUILD_TOOLS_DIR.is_dir():
        versions = sorted((item for item in LOCAL_BUILD_TOOLS_DIR.iterdir() if item.is_dir()), key=version_key, reverse=True)
        parents.extend(versions)
        parents.append(LOCAL_BUILD_TOOLS_DIR)

    for parent in parents:
        for name in names:
            candidate = parent / name
            if candidate.is_file():
                info(f"{tool:<12}: {candidate}")
                return candidate

    die(f"Could not find '{tool}' in the SDK build-tools or in '{LOCAL_BUILD_TOOLS_DIR}'.")
    return Path("")


def find_android_jar(sdk: Path) -> Path:
    """Return the android.jar of the newest installed platform."""
    platforms = sdk / "platforms"
    if platforms.is_dir():
        installed = sorted((item for item in platforms.iterdir() if item.is_dir()), key=version_key, reverse=True)
        for platform in installed:
            candidate = platform / "android.jar"
            if candidate.is_file():
                info(f"android.jar : {candidate}")
                return candidate

    die("android.jar not found. Install a platform (SDK manager) into '<sdk>/platforms'.")
    return Path("")


def find_java_tool(name: str) -> str:
    """Resolve javac/java through JAVA_HOME first, then through PATH."""
    suffix = ".exe" if os.name == "nt" else ""
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)

    found = shutil.which(name)
    if found:
        return found

    die(f"Could not find '{name}'. Install a JDK and/or set JAVA_HOME.")
    return ""


def find_baksmali_classpath(sdk: Path) -> list[str]:
    """Collect the baksmali CLI jar and its dependencies from the SDK cmdline-tools."""
    search_roots = (sdk / "cmdline-tools", LOCAL_LIB_DIR)
    candidates: dict[str, list[Path]] = {artifact: [] for artifact in BAKSMALI_ARTIFACTS}

    for root in search_roots:
        if not root.is_dir():
            continue
        for jar in root.rglob("*.jar"):
            name = jar.stem.lower()
            for artifact in BAKSMALI_ARTIFACTS:
                if name.startswith(artifact):
                    candidates[artifact].append(jar)

    classpath: list[str] = []
    for artifact in BAKSMALI_ARTIFACTS:
        found = candidates[artifact]
        if found:
            newest = max(found, key=lambda jar: artifact_version(jar.stem.lower(), artifact))
            classpath.append(str(newest))

    has_cli = any(Path(entry).stem.lower().startswith(("smali-baksmali", "baksmali")) for entry in classpath)
    if not has_cli:
        die("baksmali CLI not found. Install the SDK command line tools (cmdline-tools) "
            f"or drop a baksmali jar into '{LOCAL_LIB_DIR}'.")

    info(f"baksmali    : {Path(classpath[0]).name} (+{len(classpath) - 1} dependency jars)")
    return classpath


def build_native(ndk_build: Path) -> None:
    """Compile arcaea_patcher/native and copy the produced libneki.so files into templates."""
    application_mk = NATIVE_DIR / "Application.mk"
    if not application_mk.is_file():
        die(f"Missing '{application_mk}'")

    info("Compiling native sources with ndk-build...")
    # ndk-build only looks for '<project>/jni/Application.mk' and derives the project
    # folder from AndroidManifest.xml/jni/Android.mk, so both paths are forced here.
    # The working directory must stay in native/, because Application.mk points
    # APP_BUILD_SCRIPT to the relative 'Android.mk'.
    argv = as_command(ndk_build) + [
        f"NDK_PROJECT_PATH={NATIVE_DIR}",
        f"NDK_APPLICATION_MK={application_mk}",
    ]
    run(argv, cwd=NATIVE_DIR, label="ndk-build")

    libs_dir = NATIVE_DIR / "libs"
    if not libs_dir.is_dir():
        die(f"ndk-build did not create '{libs_dir}'")

    copied = 0
    for abi_dir in sorted(item for item in libs_dir.iterdir() if item.is_dir()):
        built_so = abi_dir / "libneki.so"
        if not built_so.is_file():
            warn(f"No libneki.so produced for ABI '{abi_dir.name}', skipped")
            continue
        target = TEMPLATES_DIR / "lib" / abi_dir.name / "libneki.so"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_so, target)
        success(f"{target.relative_to(ROOT_DIR)}  ({target.stat().st_size} bytes)")
        copied += 1

    if copied == 0:
        die("No native library was produced.")


def build_java(javac: str, java: str, android_jar: Path, d8: Path, baksmali_classpath: list[str]) -> None:
    """Compile arcaea_patcher/java into smali and write it into templates/smali_classes3."""
    sources = sorted(JAVA_DIR.rglob("*.java"))
    if not sources:
        die(f"No java sources found in '{JAVA_DIR}'")

    output_dir = TEMPLATES_DIR / "smali_classes3"
    output_dir.mkdir(parents=True, exist_ok=True)

    info(f"Compiling {len(sources)} java source(s) into smali...")
    with tempfile.TemporaryDirectory(prefix="neki-bake-") as tmp:
        tmp_dir = Path(tmp)
        classes_dir = tmp_dir / "classes"
        dex_dir = tmp_dir / "dex"
        classes_dir.mkdir()
        dex_dir.mkdir()

        run(
            [javac, "-source", JAVA_SOURCE_LEVEL, "-target", JAVA_SOURCE_LEVEL, "-Xlint:-options",
             "-encoding", "UTF-8", "-classpath", str(android_jar), "-d", str(classes_dir)]
            + [str(source) for source in sources],
            label="javac",
        )

        class_files = sorted(classes_dir.rglob("*.class"))
        if not class_files:
            die("javac produced no class files")

        run(
            as_command(d8) + ["--min-api", str(MIN_API), "--lib", str(android_jar), "--output", str(dex_dir)]
            + [str(class_file) for class_file in class_files],
            label="d8",
        )

        dex_file = dex_dir / "classes.dex"
        if not dex_file.is_file():
            die("d8 produced no classes.dex")

        run(
            [java, "-cp", os.pathsep.join(baksmali_classpath), BAKSMALI_MAIN_CLASS, "disassemble",
             "--api", str(MIN_API), "--use-locals", "--output", str(output_dir), str(dex_file)],
            label="baksmali",
        )

    smali_files = sorted(output_dir.rglob("*.smali"))
    if not smali_files:
        die("baksmali produced no smali files")

    for smali_file in smali_files:
        success(f"{smali_file.relative_to(ROOT_DIR)}  ({smali_file.stat().st_size} bytes)")


def main() -> None:
    info("Detecting Android SDK...")
    sdk = find_android_sdk()
    ndk_build = find_ndk_build(sdk)
    d8 = find_host_tool(sdk, "d8")
    android_jar = find_android_jar(sdk)
    javac = find_java_tool("javac")
    java = find_java_tool("java")
    baksmali_classpath = find_baksmali_classpath(sdk)

    build_native(ndk_build)
    build_java(javac, java, android_jar, d8, baksmali_classpath)

    print()
    success(f"Done. Templates are ready in: {TEMPLATES_DIR}")
    info("Copy that folder into the root of the decompiled APK.")


if __name__ == "__main__":
    main()


# Arcaea Lite Patcher

A modular, lightweight, and automated Python tool designed to unpack, patch, rebuild, and sign Arcaea (and similar Cocos2d-based) Android APKs.

This tool focuses on:
- **Universal SSL Pinning Bypass** (Native OpenSSL hooks + Java `Cocos2dxHttpURLConnection` bypass).
- **Network Security Configuration Injection** (Permits user CA certificates for proxies like Reqable, HttpCanary, Mitmproxy, and Charles).
- **Dynamic Domain Redirection** (Java bytecode string substitution with unlimited domain length).

---

## 🛠️ Prerequisites & Setup

### 1. Python 3.8+
Ensure [Python](https://www.python.org/downloads/) (version 3.8 or higher) is installed and added to your system `PATH`.

Install required Python dependencies:
```bash
pip install pyyaml
```

### 2. Java (JDK / JRE)
Java is required to execute Apktool and Apksigner.
- 📥 **Download**: [Eclipse Temurin (Adoptium)](https://adoptium.net/temurin/releases)
- **Note**: Install Java 11, 17, or 21 LTS. Ensure the installer option **"Add to PATH"** is enabled so `java` and `keytool` are accessible from your terminal.

### 3. Apktool
Used for disassembling and building the APK package.
- 📥 **Download**: [Apktool Releases (GitHub)](https://github.com/ibotpeaches/apktool/releases)
- **Instructions**:
  1. Download the latest `apktool_x.x.x.jar`.
  2. Rename it to `apktool.jar`.
  3. Place it inside the `lib/` directory (or add it directly to your system `PATH`).

### 4. Android SDK Build-Tools
Provides `zipalign` and `apksigner`.

You can use **any** of the following methods (the toolchain will auto-discover the newest version):
- **Option A (System Android SDK):** If you have Android Studio or the SDK installed, ensure `ANDROID_HOME` or `ANDROID_SDK_ROOT` is set in your environment variables.
- **Option B (Standalone Directory):** Download build-tools from [Android SDK Manager Web Mirror](https://androidsdkmanager.azurewebsites.net/build_tools.html), extract the archive (e.g. version `34.0.0`, `33.0.2`, etc.), and place the folder directly inside `build-tools/`.
- **Option C (System PATH):** Install `zipalign` and `apksigner` using your OS package manager (`apt`, `brew`, etc.) so they are available in your `PATH`.

---

## 📁 Project Structure

```text
Project_Root/
├── arcaea_patcher/                  # Core patcher package
│   ├── __init__.py
│   ├── __main__.py                  # Package execution entry point
│   ├── cli.py                       # Argument parsing & execution
│   ├── config.py                    # Configuration models & loader
│   ├── core/
│   │   ├── __init__.py
│   │   ├── apk_toolchain.py         # Dynamic SDK/toolchain locator & runner
│   │   ├── elf_patcher.py           # 32/64-bit ELF parser & binary patcher
│   │   ├── manifest_patcher.py      # Network security config & manifest injector
│   │   ├── smali_patcher.py         # Smali bytecode injector & SSL bypass
│   │   └── patch_pipeline.py        # Coordinated patching lifecycle
│   └── utils/
│       ├── __init__.py
│       └── logger.py                # Color terminal logger
├── lib/
│   └── apktool.jar                  # (Optional if apktool is in PATH)
├── build-tools/                     # (Optional if SDK is in PATH or ANDROID_HOME)
│   └── 34.0.0/                      # Any version folder name
│       ├── zipalign
│       └── lib/
│           └── apksigner.jar
└── config.yml                       # Optional configuration file
```

---

## 🚀 Usage & CLI Commands

### 1. Basic SSL Pinning Bypass (Default)
Unpacks the APK, bypasses native/Java SSL pinning, injects network security configuration, and re-signs with an auto-generated debug keystore:

```bash
python -m arcaea_patcher path/to/input.apk -o path/to/patched.apk
```

### 2. Custom Domain Redirection via CLI
Replace the official API and Authentication servers with custom private server endpoints:

```bash
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host my-api.example.com \
  --auth-host my-auth.example.com
```

### 3. Using an Optional Configuration File
For custom keystores or advanced domain replacement rules, pass a YAML configuration file with `-c` or `--config`:

```bash
python -m arcaea_patcher input.apk -o patched.apk -c config.yml
```

---

## ⚙️ Configuration (`config.yml` - Optional)

The configuration file is **completely optional**. If provided, it can specify custom signing credentials and extra domain mapping rules:

```yaml
# Custom Domain Routing (Overrides defaults)
server:
  api_host: "custom-api.example.com"
  auth_host: "custom-auth.example.com"
  custom_mappings:
    "example-old.lowiro.com": "example-new.domain.com"

# Custom Signing Configuration
# If the specified keystore does not exist, a debug keystore will be generated automatically.
signing:
  keystore: "debug.keystore"
  alias: "androiddebugkey"
  keystore_password: "android"
  key_password: "android"
```

---

## 🔍 CLI Reference

```text
usage: arcaea_patcher [-h] -o OUTPUT [-c CONFIG] [--api-host API_HOST] [--auth-host AUTH_HOST] input

Modular Android APK Security & Network Routing Patcher

positional arguments:
  input                 Path to the original input APK file

options:
  -h, --help            Show this help message and exit
  -o, --output OUTPUT   Destination path for the patched APK file
  -c, --config CONFIG   Optional YAML configuration file for custom settings
  --api-host API_HOST   Custom hostname to replace API endpoints
  --auth-host AUTH_HOST Custom hostname to replace Authentication endpoints
```

---

## ⚠️ Troubleshooting

- **`Required tool not found: java` / `keytool`**:
  Ensure Java JDK is installed from [Adoptium](https://adoptium.net/temurin/releases) and the `bin` directory is added to your environment `PATH`. Restart your terminal after installing.
- **`Could not find 'zipalign'` / `'apksigner'`**:
  Make sure you either:
  1. Set `ANDROID_HOME` pointing to your Android SDK.
  2. Put a build-tools folder inside `build-tools/` (e.g. `build-tools/34.0.0/`).
  3. Install `zipalign` and `apksigner` in your system `PATH`.
- **Apktool Decompilation Errors**:
  Make sure you are using the newest release of `apktool.jar` from [Apktool Releases](https://github.com/ibotpeaches/apktool/releases).
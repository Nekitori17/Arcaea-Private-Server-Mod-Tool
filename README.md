# Arcaea Private Server Patcher - v7.0.1c

A modular, lightweight, and automated Python tool designed to unpack, patch, rebuild, and sign Arcaea (and similar Cocos2d-based) Android APKs for custom server routing and certificate verification adjustments.

This tool focuses on:

- **Native & Java SSL Verification Bypass**: Patches native OpenSSL routines (`SSL_CTX_set_verify`, `X509_verify_cert`, `SSL_get_verify_result`) and Java `Cocos2dxHttpURLConnection`.
- **Dynamic Native Hook Domain Redirection (`libneki.so`)**: Uses PLT hooking to intercept and redirect DNS lookups and network requests seamlessly at runtime without domain length limits!
- **Storage Access Framework Integration**: Exposes internal app data directory (`/data/data/<pkg>`) for file managers without root.
- **Automated Build & Signing Pipeline**: Auto-discovers Android SDK build-tools, handles alignment with `zipalign`, and signs with `apksigner`.

---

## 🚀 Dynamic Domain Routing (`domain.cfg`)

Domain redirection is handled at runtime by `libneki.so` (pre-compiled for both **armeabi-v7a** and **arm64-v8a**).
- **No string length limits**: Route to any domain name or IP address.
- **Runtime editable**: `domain.cfg` is generated automatically from your `config.yml` during patching, and can also be modified in internal storage.

---

## 🛠️ Prerequisites & Setup

### 1. Python 3.8+

Ensure [Python](https://www.python.org/downloads/) is installed and added to your system `PATH`.

Install required dependencies:

```bash
pip install pyyaml
```

### 2. Java (JDK / JRE)

Java is required to run Apktool and Apksigner.

- 📥 **Download**: [Eclipse Temurin (Adoptium)](https://adoptium.net/temurin/releases)
- **Instructions**: Install Java (11, 17, or 21 LTS). Make sure **"Add to PATH"** is enabled so `java` and `keytool` work in your terminal.

### 3. Apktool

Used for decompiling and rebuilding the APK.

- 📥 **Download**: [Apktool Releases (GitHub)](https://github.com/ibotpeaches/apktool/releases)
- **Instructions**:
  1. Download the latest `apktool_x.x.x.jar`.
  2. Rename it to `apktool.jar`.
  3. Place it inside the `lib/` folder (or install it in your system `PATH`).

### 4. Android SDK Build-Tools

Provides `zipalign` and `apksigner`.

The toolchain automatically detects the newest available build-tools from:

- **Option A (System Android SDK)**: Environment variables `ANDROID_HOME` or `ANDROID_SDK_ROOT`.
- **Option B (Local Folder)**: Place an extracted build-tools version folder (e.g. `34.0.0`) inside the `build-tools/` directory. [Build Tools Release](https://androidsdkmanager.azurewebsites.net/build_tools.html)
- **Option C (System PATH)**: `zipalign` and `apksigner` installed directly on your system.

---

## 📁 Project Structure

```text
Project_Root/
├── arcaea_patcher/                  # Core patcher package
│   ├── __init__.py
│   ├── __main__.py                  # Package execution entry point
│   ├── cli.py                       # CLI parser & execution flow
│   ├── config.py                    # Configuration models & loader
│   ├── core/
│   │   ├── __init__.py
│   │   ├── apk_toolchain.py         # Dynamic SDK/toolchain locator & runner
│   │   ├── elf_patcher.py           # 32/64-bit ELF parser & Native SSO patcher
│   │   ├── manifest_patcher.py      # Network security config injector
│   │   ├── smali_patcher.py         # Smali Java SSL bypass
│   │   └── patch_pipeline.py        # Coordinated patching lifecycle
│   └── utils/
│       ├── __init__.py
│       └── logger.py                # Color terminal logger
├── lib/
│   └── apktool.jar                  # (Optional if apktool is in PATH)
├── build-tools/                     # (Optional if SDK is in PATH or ANDROID_HOME)
│   └── 34.0.0/                      # Any build-tools version folder
│       ├── zipalign
│       └── lib/
│           └── apksigner.jar
└── config.yml                       # Optional configuration file
```

---

## 🚀 Usage & CLI Commands

### 1. Basic SSL Pinning Bypass (Default)

Unpacks the APK, applies native and Java verification bypasses, and re-signs with an auto-generated debug keystore:

```bash
python -m arcaea_patcher input.apk -o patched.apk
```

### 2. Custom Domain Redirection via CLI

Redirect API and Authentication traffic to your private server:

```bash
# Example with separate hosts
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host arc-api.nekitori17.com \
  --auth-host au-v2.nekitori17.com

# Example with a unified host (<= 18 characters)
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host ar-sv.nekitori17.com \
  --auth-host ar-sv.nekitori17.com
```

### 3. Using an Optional Configuration File

```bash
python -m arcaea_patcher input.apk -o patched.apk -c config.yml
```

---

## ⚙️ Configuration (`config.yml` - Optional)

You can define custom hostnames and signing credentials via YAML:

```yaml
# Custom Domain Routing
# Supports any domain length or IP address!
server:
  api_host: "arc-api.nekitori17.com"
  auth_host: "ar-au.nekitori17.com"

# Custom Package Name (Optional)
# Change the APK package name to install alongside the original app
package_name: "moe.neki.arc"

features:
  # Expose Internal App Data via Storage Access Framework
  expose_internal_data: false

# Custom Signing Configuration
# If the keystore does not exist, a debug keystore will be generated automatically.
signing:
  keystore: "debug.keystore"
  alias: "androiddebugkey"
  keystore_password: "android"
  key_password: "android"
```

---

## 🔍 CLI Options

```text
usage: arcaea_patcher [-h] -o OUTPUT [-c CONFIG] [--api-host API_HOST] [--auth-host AUTH_HOST] input

Modular Android APK Security & Network Routing Patcher

positional arguments:
  input                 Path to original input APK file

options:
  -h, --help            Show this help message and exit
  -o, --output OUTPUT   Destination path for the patched APK file
  -c, --config CONFIG   Optional YAML configuration file
  --api-host API_HOST   Custom hostname for API endpoints
  --auth-host AUTH_HOST Custom hostname for Auth endpoints
  --package-name PKG    Custom package name for the patched APK
```

---

## ⚠️ Troubleshooting

- **`Required tool not found: java` / `keytool`**:
  Ensure Java JDK is installed from [Adoptium](https://adoptium.net/temurin/releases) and added to your system `PATH`. Restart your terminal after installation.
- **`Could not find 'zipalign'` / `'apksigner'`**:
  Make sure you either set `ANDROID_HOME`, place an extracted build-tools directory in `build-tools/`, or install `zipalign` in your system `PATH`.

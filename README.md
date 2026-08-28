# Arcaea Private Server Patcher - v6.16.8c

A modular, lightweight, and automated Python tool designed to unpack, patch, rebuild, and sign Arcaea (and similar Cocos2d-based) Android APKs for custom server routing and certificate verification adjustments.

This tool focuses on:

- **Native & Java SSL Verification Bypass**: Patches native OpenSSL routines (`SSL_CTX_set_verify`, `X509_verify_cert`, `SSL_get_verify_result`) and Java `Cocos2dxHttpURLConnection`.
- **Native Assembly & `.rodata` Domain Redirection**: Patches hardcoded domain strings and reconstructs inline C++ `std::string` SSO (Short String Optimization) structures in `libcocos2dcpp.so`.
- **Automated Build & Signing Pipeline**: Auto-discovers Android SDK build-tools, handles alignment with `zipalign`, and signs with `apksigner`.

---

## ⚠️ Important: Domain Length Limits

Due to native C++ `std::string` stack buffer (SSO) constraints inside `libcocos2dcpp.so`, custom hostnames must **not** exceed the maximum length of the original buffers:

| Target Endpoint               | Original Domain        |     Max Length     | Example                      |
| :---------------------------- | :--------------------- | :----------------: | :--------------------------- |
| **API Host** (`--api-host`)   | `arcapi-v4.lowiro.com` | **$\le$ 20 chars** | `arc-api.nekitori.com` (20B) |
| **Auth Host** (`--auth-host`) | `auth-v2.lowiro.com`   | **$\le$ 18 chars** | `au-v2.nekitori.com` (18B)   |
| **Unified Host** (Combined)   | _Both endpoints_       | **$\le$ 18 chars** | `ar-sv.nekitori.com` (18B)   |

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
# api_host MUST be <= 20 bytes
# auth_host MUST be <= 18 bytes
server:
  api_host: "arc-api.nekitori17.com"
  auth_host: "ar-au.nekitori17.com"

# Custom Package Name (Optional)
# Change the APK package name to install alongside the original app
package_name: "moe.low.arc.custom"

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
  --api-host API_HOST   Custom hostname for API endpoints (max 20 chars)
  --auth-host AUTH_HOST Custom hostname for Auth endpoints (max 18 chars)
  --package-name PKG    Custom package name for the patched APK
```

---

## ⚠️ Troubleshooting

- **`Required tool not found: java` / `keytool`**:
  Ensure Java JDK is installed from [Adoptium](https://adoptium.net/temurin/releases) and added to your system `PATH`. Restart your terminal after installation.
- **`Could not find 'zipalign'` / `'apksigner'`**:
  Make sure you either set `ANDROID_HOME`, place an extracted build-tools directory in `build-tools/`, or install `zipalign` in your system `PATH`.
- **Hostname exceeded buffer warning**:
  Ensure your `--api-host` is $\le 20$ characters and `--auth-host` is $\le 18$ characters. If your domain is longer, use a shorter subdomain or custom domain.

# Arcaea Private Server Patcher - v7.0.1c

A modular, lightweight, and automated Python tool designed to unpack, patch, rebuild, and sign Arcaea (and similar Cocos2d-based) Android APKs for custom server routing and certificate verification adjustments.

This tool focuses on:

- **Native & Java SSL Verification Bypass**: Neutralises native OpenSSL/BoringSSL routines (`SSL_CTX_set_verify`, `SSL_set_verify`, `SSL_CTX_set_custom_verify`, `SSL_CTX_set_cert_verify_callback`, `SSL_set1_host`, `X509_verify_cert`, `SSL_get_verify_result`) with an ARM32/ARM64 (Thumb-aware, idempotent) binary patcher, installs runtime PLT hooks via `libneki.so`, and patches the Java `Cocos2dxHttpURLConnection` helpers (`setVerifySSL`, `verifySSLPins`). `SSL_CTX_set_cert_verify_callback` is patched because Arcaea registers its own certificate-pinning callback through it; without the patch the client completes the TLS handshake but tears it down before sending any HTTP request, which shows up as "Could not connect to online server".
- **Dynamic Native Hook Domain Redirection (`libneki.so`)**: PLT-hooks `getaddrinfo` / `connect` / `gethostbyname` inside `libcocos2dcpp.so` and redirects name lookups and connections at runtime without domain length limits.
- **Storage Access Framework Integration**: Exposes internal app data directory (`/data/data/<pkg>`) for file managers without root.
- **Automated Build & Signing Pipeline**: Auto-discovers Android SDK build-tools, handles alignment with `zipalign`, and signs with `apksigner`.

---

## 🧱 Step 0 — Bake the templates (`complie.py`)

The patcher injects pre-built artifacts (`libneki.so` + compiled Java classes) from `arcaea_patcher/templates/`. Bake them once — and again whenever `arcaea_patcher/native` or `arcaea_patcher/java` changes:

```bash
python complie.py
```

`complie.py` auto-detects the Android SDK (`ANDROID_HOME` / `ANDROID_SDK_ROOT` / default install locations) and performs two independent builds:

1. **Native** — compiles `arcaea_patcher/native` with `ndk-build` and copies every produced library to `arcaea_patcher/templates/lib/<abi>/libneki.so` (`armeabi-v7a` + `arm64-v8a`).
2. **Java** — compiles `arcaea_patcher/java` with `javac`, converts the classes with `d8` and disassembles them with `baksmali` into `arcaea_patcher/templates/smali_classes3/moe/neki/arc/*.smali`.

The resulting `templates/` folder mirrors the layout of a decoded (apktool) APK, so during patching the pipeline merges it into the decompiled folder **in one step** (files with the same path are overwritten):

```text
arcaea_patcher/templates/
├── lib/armeabi-v7a/libneki.so          ->  lib/armeabi-v7a/libneki.so
├── lib/arm64-v8a/libneki.so            ->  lib/arm64-v8a/libneki.so
└── smali_classes3/moe/neki/arc/*.smali ->  smali_classes3/...  (apktool packs it as classes3.dex)
```

Requirements used by `complie.py`:

- JDK (`javac`, `java`) through `JAVA_HOME` or `PATH`.
- Android SDK with an **NDK**, **build-tools** (`d8`), at least one **platform** (`android.jar`) and the **command line tools** (baksmali jars), or drop the baksmali `*.jar` files into `lib/`.

If the templates were not baked, the pipeline only logs a warning and produces an APK **without** `libneki.so` / the injected Java classes.

---

## 🚀 Dynamic Domain Routing (`domain.cfg`)

Domain redirection is handled at runtime by `libneki.so` (built by `complie.py` for both **armeabi-v7a** and **arm64-v8a**).

- **No string length limits**: route to any domain name or IP address.
- **Runtime editable**: `domain.cfg` is generated from your `config.yml` during patching and extracted from the APK assets only **when missing**, so edits made in internal storage (e.g. through the Storage Access Framework provider) survive app restarts — delete the file to restore the APK default.

---

## 🛠️ Prerequisites & Setup

### 1. Python 3.9+

Ensure [Python](https://www.python.org/downloads/) is installed and added to your system `PATH`.

Install required dependencies:

```bash
pip install pyyaml
```

### 2. Java (JDK / JRE)

Java is required to run Apktool, Apksigner and `complie.py`.

- 📥 **Download**: [Eclipse Temurin (Adoptium)](https://adoptium.net/temurin/releases)
- **Instructions**: Install Java (11, 17, or 21 LTS). Make sure **"Add to PATH"** is enabled so `java`, `javac` and `keytool` work in your terminal.

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

### 5. Android NDK & Command Line Tools (only for `complie.py`)

- Install the **NDK** and the **SDK command line tools** through Android Studio (SDK Manager) or `sdkmanager`.
- `complie.py` also needs a platform (`<sdk>/platforms/<ver>/android.jar`) and build-tools providing `d8`.
- See **Step 0 — Bake the templates (`complie.py`)** above for the full workflow.

---

## 📁 Project Structure

```text
Project_Root/
├── arcaea_patcher/                  # Core patcher package
│   ├── __init__.py / __main__.py    # Package version + execution entry point
│   ├── cli.py                       # CLI parser & execution flow
│   ├── config.py                    # Configuration models & loader
│   ├── constants.py                 # Default API/Auth domain lists
│   ├── core/
│   │   ├── apk_toolchain.py         # Dynamic SDK/toolchain locator & runner
│   │   ├── elf_patcher.py           # ELF parser + native SSL bypass patcher (ARM32/ARM64)
│   │   ├── manifest_patcher.py      # Manifest / NSC / DocumentsProvider injector
│   │   ├── smali_patcher.py         # Java SSL pinning bypass + native hook trigger
│   │   └── patch_pipeline.py        # Coordinated patching lifecycle
│   ├── java/                        # Java sources baked into smali (NekiLoader, provider)
│   ├── native/                      # C sources baked into libneki.so
│   │   ├── Android.mk / Application.mk / Main.c
│   │   ├── core/                    # HookEngine, RouteCache
│   │   ├── hooks/                   # DomainRedirectHook, SSLPinningHook
│   │   └── utils/                   # DomainParser, FileUtils, MemoryUtils, Logger.h
│   ├── templates/                   # Baked artifacts (generated by complie.py)
│   └── utils/
│       ├── __init__.py
│       └── logger.py                # Color terminal logger
├── complie.py                       # Bakes arcaea_patcher/native + java into templates/
├── gen_cert.py                      # (Optional) helper to generate the MITM certificate
├── lib/
│   └── apktool.jar                  # (Optional if apktool is in PATH)
├── build-tools/                     # (Optional if SDK is in PATH or ANDROID_HOME)
│   └── 34.0.0/                      # Any build-tools version folder
│       ├── zipalign
│       └── lib/
│           └── apksigner.jar
├── config.yml                       # Optional configuration file
└── config.example.yml               # Example configuration
```

---

## 🚀 Usage & CLI Commands

### 1. Bake the templates (first run / after changing native or java sources)

```bash
python complie.py
```

### 2. Basic SSL Pinning Bypass (Default)

Unpacks the APK, applies native and Java verification bypasses, and re-signs with an auto-generated debug keystore:

```bash
python -m arcaea_patcher input.apk -o patched.apk
```

### 3. Custom Domain Redirection via CLI

Redirect API and Authentication traffic to your private server:

```bash
# Example with separate hosts
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host arc-api.nekitori17.com \
  --auth-host au-v2.nekitori17.com

# Example with a unified host
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host ar-sv.nekitori17.com \
  --auth-host ar-sv.nekitori17.com
```

### 4. Using an Optional Configuration File

```bash
python -m arcaea_patcher input.apk -o patched.apk -c config.yml
```

---

## 🔧 How the patching pipeline works

`python -m arcaea_patcher` runs these steps (`core/patch_pipeline.py`):

1. Decompiles the input APK with apktool.
2. Merges the baked `templates/` tree (native libs + Java smali) into the decoded folder.
3. Renames the package — and every package-derived identifier such as custom permission names — when `package_name` is set.
4. Injects a permissive Network Security Config (system + user CAs, cleartext allowed).
5. Injects the Storage Access Framework provider (when `expose_internal_data: true`).
6. Writes `assets/domain.cfg` and injects the native hook trigger (when a server host is configured).
7. Patches `libcocos2dcpp.so` (ARM32/ARM64, Thumb-aware) to neutralise OpenSSL verification.
8. Patches the `Cocos2dxHttpURLConnection` smali to bypass Java-level SSL pinning.
9. Rebuilds with apktool, aligns with `zipalign` and signs with `apksigner`.

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
usage: apk_patcher [-h] -o OUTPUT [-c CONFIG] [--api-host API_HOST] [--auth-host AUTH_HOST]
                   [--package-name PACKAGE_NAME] input

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

- **`Could not find 'apktool'`**: place `apktool.jar` inside `lib/` or add `apktool` to your `PATH`.
- **Java / `keytool` not found**: install a JDK from [Adoptium](https://adoptium.net/temurin/releases) and make sure `JAVA_HOME` (or `PATH`) points to it. Restart your terminal after installation.
- **`Could not find 'zipalign'` / `'apksigner'`**: make sure you either set `ANDROID_HOME`, place an extracted build-tools directory in `build-tools/`, or install `zipalign` in your system `PATH`.
- **`Android SDK not found`** (from `complie.py`): set `ANDROID_HOME` (or `ANDROID_SDK_ROOT`) to your SDK folder.
- **`ndk-build` not found**: install an NDK through the SDK Manager or set `ANDROID_NDK_HOME`.
- **`baksmali CLI not found`**: install the SDK command line tools (`cmdline-tools`) or drop the baksmali `*.jar` files into `lib/`.
- **`Templates directory not found` / `No template files merged`**: run `python complie.py` before patching.
- **Game logs `Rule[...] -> <ip>` but still shows "Could not connect"**: make sure the `domain.cfg` on device has no stray bytes — the patcher now sanitises control characters/quotes when generating it, and `NekiLoader` re-extracts it from the APK assets if it is malformed. Delete `/data/user/0/<pkg>/files/domain.cfg` to force a refresh.

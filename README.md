# Arcaea Private Server Patcher - v7.0.260c

Python CLI that takes an Arcaea APK, disables SSL certificate/pinning checks (native + Java), redirects API/Auth traffic to your own server at runtime, then rebuilds, aligns and signs the APK.

## What it does

- **SSL bypass (static + runtime)** — patches `libcocos2dcpp.so` (ARM32/ARM64, Thumb-aware, idempotent) to neutralize `SSL_CTX_set_verify`, `SSL_CTX_set_custom_verify`, `SSL_CTX_set_cert_verify_callback`, `X509_verify_cert`, `SSL_set1_host`, plus curl's pinned-public-key check; and neutralizes `setVerifySSL` / `verifySSLPins` in `Cocos2dxHttpURLConnection.smali`.
- **Domain redirection** — writes `assets/domain.cfg` (`original=replacement` rules) and injects `NekiLoader`, which loads `libneki.so`. The library PLT-hooks `getaddrinfo` / `gethostbyname` / `gethostbyname2` / `connect` inside `libcocos2dcpp.so`. No domain length limit; hostnames, `host:port` and raw IPs are supported.
- **Network Security Config** — injected so the app trusts system + user CAs and allows cleartext (required for MITM / self-signed private servers).
- **Optional features** — package rename (install side-by-side with the original app), Storage Access Framework provider (browse `/data/data/<pkg>` from a file manager, no root).
- **Automated build** — apktool rebuild → `zipalign` → `apksigner`, with automatic tool discovery.

## Requirements

| Dependency | Needed for | Where to get it |
|---|---|---|
| Python 3.9+ with `pip install pyyaml` | patcher | [python.org](https://www.python.org/downloads/) |
| JDK 11/17/21 (`java`, `javac`, `keytool` on PATH) | apktool, signing, `complie.py` | [Eclipse Temurin](https://adoptium.net/temurin/releases) |
| `apktool.jar` | decompile/rebuild | [apktool releases](https://github.com/ibotpeaches/apktool/releases) — rename to `apktool.jar`, drop into `lib/` (or put `apktool` on PATH) |
| Android build-tools (`zipalign`, `apksigner`) | align + sign | [build-tools archives](https://androidsdkmanager.azurewebsites.net/build_tools.html) — see discovery order below |
| Android NDK + cmdline-tools | **only** `complie.py` | SDK Manager (Android Studio / `sdkmanager`) |

Build-tools are resolved in this order:

1. `build-tools/` in the project root (extracted version folder, e.g. `build-tools/34.0.0/`)
2. `$ANDROID_HOME` / `$ANDROID_SDK_ROOT` → `build-tools/` (newest version wins)
3. OS default SDK locations (`%LOCALAPPDATA%\Android\Sdk`, `~/Android/Sdk`, …)
4. `zipalign` / `apksigner` on system PATH

## Quick start

```bash
pip install pyyaml

# 1. put apktool.jar in lib/
# 2. provide build-tools (folder above or ANDROID_HOME)

# 3. configure your server (or skip and use CLI flags / default SSL-bypass-only mode)
cp config.example.yml config.yml

# 4. patch
python -m arcaea_patcher arcaea_7.0.260c.apk -o patched.apk
```

CLI flags override `config.yml`. `config.yml` / `config.yaml` in the project root is picked up automatically.

```bash
python -m arcaea_patcher input.apk -o patched.apk \
  --api-host arc-api.example.com \
  --auth-host auth.example.com \
  --package-name moe.neki.arc
```

The APK is signed with `debug.keystore` (auto-generated on first run) unless you change the `signing:` section. The original signature will not be preserved — uninstall the original app if the package name is unchanged.

## Configuration (`config.yml`)

```yaml
server:
  api_host: "arc-api.example.com"      # replaces arcapi-v4/v3.lowiro.com
  auth_host: "auth.example.com:8080"   # replaces auth-v2/auth/arcaea.lowiro.com
  custom_mappings:                     # optional extra rules, one per entry
    "some.other.host": "192.168.1.10"

package_name: "moe.neki.arc"           # omit to keep the original package

features:
  expose_internal_data: false          # SAF provider for internal storage access

signing:
  keystore: "debug.keystore"
  alias: "androiddebugkey"
  keystore_password: "android"
  key_password: "android"
```

If no `server:` host is set, the tool runs in SSL-bypass-only mode (no redirection).

## Pipeline

`python -m arcaea_patcher` executes (see `arcaea_patcher/core/patch_pipeline.py`):

1. Decompile with apktool
2. Merge pre-built `templates/` (libneki.so + NekiLoader/InternalStorageProvider smali)
3. Rename package (when configured) — including app-owned custom permissions
4. Inject Network Security Config
5. Inject Storage Access Framework provider (when enabled)
6. Write `assets/domain.cfg` + inject `NekiLoader.init()` into the main Activity
7. Patch `libcocos2dcpp.so` (ELF-level SSL bypass, both ABIs)
8. Patch Java-level SSL pinning in smali
9. Rebuild → `zipalign` → `apksigner`

## On-device behavior

- `NekiLoader` runs in the launcher Activity's `onCreate`. It copies `assets/domain.cfg` to `/data/user/0/<pkg>/files/domain.cfg` **only when missing or malformed**, then loads `libneki.so` and installs the hooks.
- Edit `files/domain.cfg` on device to change routing without re-patching (needs `expose_internal_data: true` or root). Delete the file to restore the APK's default.
- Redirect log lines appear in logcat under `NekiLoader` / `libneki` / `DomainRedirect`.

## Rebuilding the injected artifacts (`complie.py`)

`arcaea_patcher/templates/` (libneki.so for both ABIs + compiled smali) is **committed to the repo**, so you only need this when you modify `arcaea_patcher/native/` or `arcaea_patcher/java/`:

```bash
python complie.py
```

Requires an Android SDK visible through `ANDROID_HOME` / `ANDROID_SDK_ROOT` with:

- an **NDK** (`ndk-build`)
- **build-tools** providing `d8`
- at least one **platform** (`android.jar`)
- **cmdline-tools** (baksmali jars) — or drop the baksmali `*.jar` files into `lib/`
- a JDK (`javac`, `java`)

If `templates/` is missing, patching still succeeds but produces an APK **without** domain redirection.

## Optional: server certificate (`gen_cert.py`)

Generates `server.pem` + `server.key` (RSA-2048, 10 years) with SANs covering the `lowiro.com` domains, `localhost` and any hosts/IPs listed in `config.yml` — for running your private server behind TLS.

```bash
pip install cryptography
python gen_cert.py
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `apktool not found` | Place `apktool.jar` in `lib/` or add `apktool` to PATH |
| `zipalign not found` / `apksigner not found` | Set `ANDROID_HOME`, or put an extracted build-tools folder in `build-tools/`, or install them on PATH |
| `keytool` / Java not found | Install a JDK, ensure `java`/`javac`/`keytool` are on PATH, restart the terminal |
| `Templates directory not found` | `templates/` is missing — restore it from git or run `python complie.py` |
| `Android SDK not found` / `ndk-build not found` (from `complie.py`) | Set `ANDROID_HOME` (or `ANDROID_SDK_ROOT`) and install the NDK via SDK Manager |
| `baksmali CLI not found` | Install SDK cmdline-tools, or drop the baksmali jars into `lib/` |
| Game logs redirect rules but still says "Could not connect" | Delete `/data/user/0/<pkg>/files/domain.cfg` to force re-extraction, then check logcat for `NekiLoader` errors |
| App connects but TLS still fails | The NSC trusts system + user CAs — install your server's CA/certificate on the device |

## Project structure

```text
├── arcaea_patcher/
│   ├── cli.py / config.py / constants.py    # CLI, YAML config loader, default domains
│   ├── core/
│   │   ├── patch_pipeline.py                # 9-step orchestration
│   │   ├── apk_toolchain.py                 # tool discovery (apktool/build-tools/signing)
│   │   ├── elf_patcher.py / pin_patcher.py  # native SSL bypass
│   │   ├── smali_patcher.py                 # Java SSL bypass + NekiLoader injection
│   │   ├── manifest_patcher.py              # package rename, NSC, SAF provider
│   │   └── domain_patcher.py                # domain.cfg generation
│   ├── java/                                # NekiLoader, InternalStorageProvider (source)
│   ├── native/                              # libneki.so sources (NDK)
│   └── templates/                           # pre-built artifacts merged into the APK
├── complie.py                               # rebuild templates/ from java/ + native/
├── gen_cert.py                              # optional TLS cert generator
├── config.example.yml                       # copy to config.yml
├── lib/apktool.jar                          # you provide (not in git)
└── build-tools/                             # you provide (not in git)
```

## License

[MIT](LICENSE)


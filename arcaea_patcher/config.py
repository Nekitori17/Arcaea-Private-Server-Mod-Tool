from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import yaml


@dataclass
class ServerRoutingConfig:
    api_host: Optional[str] = None
    auth_host: Optional[str] = None
    custom_mappings: Dict[str, str] = field(default_factory=dict)


@dataclass
class SigningConfig:
    keystore_path: Path = Path("debug.keystore")
    alias: str = "androiddebugkey"
    keystore_password: str = "android"
    key_password: str = "android"


@dataclass
class PatchConfig:
    input_apk: Path
    output_apk: Path
    server: ServerRoutingConfig = field(default_factory=ServerRoutingConfig)
    signing: SigningConfig = field(default_factory=SigningConfig)
    patch_native_ssl: bool = True
    patch_java_ssl: bool = True
    inject_nsc: bool = True

    @classmethod
    def from_yaml_and_args(
        cls,
        input_apk: Path,
        output_apk: Path,
        config_file: Optional[Path] = None,
        api_host: Optional[str] = None,
        auth_host: Optional[str] = None,
    ) -> "PatchConfig":
        cfg = cls(input_apk=input_apk, output_apk=output_apk)

        if config_file and config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                raw_cfg = yaml.safe_load(f) or {}

            server_data = raw_cfg.get("server", {})
            cfg.server.api_host = server_data.get("api_host")
            cfg.server.auth_host = server_data.get("auth_host")
            cfg.server.custom_mappings = server_data.get("custom_mappings", {})

            signing_data = raw_cfg.get("signing", {})
            if "keystore" in signing_data:
                cfg.signing.keystore_path = Path(signing_data["keystore"])
            cfg.signing.alias = signing_data.get("alias", cfg.signing.alias)
            cfg.signing.keystore_password = signing_data.get(
                "keystore_password", cfg.signing.keystore_password
            )
            cfg.signing.key_password = signing_data.get(
                "key_password", cfg.signing.key_password
            )

        # CLI overrides
        if api_host:
            cfg.server.api_host = api_host
        if auth_host:
            cfg.server.auth_host = auth_host

        return cfg
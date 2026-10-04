import ipaddress
from pathlib import Path
import re
from typing import List, Optional

from arcaea_patcher.config import ServerRoutingConfig
from arcaea_patcher.constants import API_DOMAINS, AUTH_DOMAINS
from arcaea_patcher.core.smali_patcher import SmaliPatcher
from arcaea_patcher.utils.logger import logger

_CONTROL_OR_QUOTE_RE = re.compile(r'[\x00-\x1f\x7f"]')
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def sanitize_host(value: Optional[str]) -> Optional[str]:
    """Strips control bytes and quotes in host string."""
    if value is None:
        return None
    cleaned = _CONTROL_OR_QUOTE_RE.sub("", value).strip()
    if cleaned != value:
        logger.warn(f"Sanitized host: {value!r} -> {cleaned!r}")
    return cleaned


def is_plausible_host(value: Optional[str]) -> bool:
    """Validates if value is a valid hostname, IP, or host:port pair."""
    if not value:
        return False
    host = value
    if ":" in value and not value.startswith("["):
        host = value.rsplit(":", 1)[0]
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.match(host))


class DomainRoutingPatcher:
    """Generates assets/domain.cfg and coordinates NekiLoader smali injection."""

    def __init__(self, decoded_dir: Path):
        self.decoded_dir = decoded_dir
        self.assets_dir = decoded_dir / "assets"

    def generate_rules(self, server_cfg: ServerRoutingConfig) -> List[str]:
        """Builds list of 'original=replacement' routing lines."""
        lines: List[str] = []
        api_host = sanitize_host(server_cfg.api_host)
        auth_host = sanitize_host(server_cfg.auth_host)

        if api_host and not is_plausible_host(api_host):
            logger.warn(f"api_host '{api_host}' may be invalid; redirect might fail")
        if auth_host and not is_plausible_host(auth_host):
            logger.warn(f"auth_host '{auth_host}' may be invalid; redirect might fail")

        if api_host:
            for d in API_DOMAINS:
                lines.append(f"{d}={api_host}")

        if auth_host:
            for d in AUTH_DOMAINS:
                lines.append(f"{d}={auth_host}")

        for orig, target in server_cfg.custom_mappings.items():
            clean_orig = sanitize_host(orig)
            clean_target = sanitize_host(target)
            if clean_orig and clean_target:
                lines.append(f"{clean_orig}={clean_target}")

        return lines

    def write_config_file(self, rules: List[str]) -> Path:
        """Writes domain.cfg to assets directory with UNIX (LF) line endings."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = self.assets_dir / "domain.cfg"
        with open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rules) + "\n")
        logger.detail(f"Created assets/domain.cfg with {len(rules)} mapping(s)")
        return cfg_path

    def apply(self, server_cfg: ServerRoutingConfig) -> int:
        """Generates domain config and injects hook trigger into entry Activity."""
        if not server_cfg.has_routing:
            return 0

        rules = self.generate_rules(server_cfg)
        if not rules:
            return 0

        self.write_config_file(rules)

        smali_patcher = SmaliPatcher(self.decoded_dir)
        smali_patcher.inject_domain_hook_loader()

        return len(rules)

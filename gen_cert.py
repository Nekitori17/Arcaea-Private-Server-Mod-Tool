import datetime
import ipaddress
from pathlib import Path
from typing import Optional

import yaml
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def load_server_ips_from_config(
    config_path: str = "config.yml",
) -> list[str]:
    """Read api_host and auth_host from config.yml, return list of unique IPs/hosts."""
    path = Path(config_path)
    if not path.exists():
        print(f"[!] Config file '{config_path}' not found, using defaults.")
        return []

    with open(path, "r", encoding="utf-8") as f:
        raw_cfg = yaml.safe_load(f) or {}

    server_data = raw_cfg.get("server") or {}
    hosts: list[str] = []
    for key in ("api_host", "auth_host"):
        host = server_data.get(key)
        if host and host not in hosts:
            hosts.append(host)

    return hosts


def generate_ssl_certificate(
    cert_path: str = "server.pem",
    key_path: str = "server.key",
    server_ip: Optional[str] = None,
    config_path: str = "config.yml",
    days_valid: int = 3650,  # 10 years
):
    # Read IP from config.yml
    config_hosts = load_server_ips_from_config(config_path)

    if config_hosts:
        print(f"[*] Loaded hosts from {config_path}: {', '.join(config_hosts)}")

    # Primary IP for Common Name (priority: parameter > config > default)
    primary_ip = server_ip or (config_hosts[0] if config_hosts else "127.0.0.1")

    print("[*] Generating 2048-bit RSA Private Key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Subject & Issuer information
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "VN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nekitori17 Arcaea Server"),
        x509.NameAttribute(NameOID.COMMON_NAME, primary_ip),
    ])

    # Domain and IP list for Subject Alternative Names (SAN)
    domains = [
        "localhost",
        "auth-v2.lowiro.com",
        "auth.lowiro.com",
        "arcapi-v4.lowiro.com",
        "arcapi-v3.lowiro.com",
        "arcaea.lowiro.com",
    ]

    # Combine IPs: 127.0.0.1 + primary_ip + all hosts from config (remove duplicates)
    ips: list[str] = ["127.0.0.1"]
    for ip in [primary_ip] + config_hosts:
        if ip not in ips:
            ips.append(ip)

    # Build SAN entries — use list[x509.GeneralName] for both DNSName and IPAddress
    alt_names: list[x509.GeneralName] = []
    for d in domains:
        alt_names.append(x509.DNSName(d))
    for ip_str in ips:
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)

    print("[*] Building X.509 Certificate with SAN extensions...")
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName(alt_names),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    # 1. Write Private Key (server.key)
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    print(f"[+] Saved Private Key to: {Path(key_path).resolve()}")

    # 2. Write Certificate (server.pem)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[+] Saved Certificate to: {Path(cert_path).resolve()}")

    print("\n[✓] Certificate generated successfully!")
    print(f"    - Valid Domains : {', '.join(domains)}")
    print(f"    - Valid IPs     : {', '.join(ips)}")


if __name__ == "__main__":
    generate_ssl_certificate()
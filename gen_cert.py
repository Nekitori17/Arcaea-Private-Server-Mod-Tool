import datetime
import ipaddress
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def generate_ssl_certificate(
    cert_path: str = "server.pem",
    key_path: str = "server.key",
    server_ip: str = "192.168.1.150",
    days_valid: int = 3650,  # 10 years
):
    print("[*] Generating 2048-bit RSA Private Key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Subject & Issuer information
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "VN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nekitori17 Arcaea Server"),
        x509.NameAttribute(NameOID.COMMON_NAME, server_ip),
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

    ips = [
        "127.0.0.1",
        server_ip,
    ]

    # Build SAN entries
    alt_names = []
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
    # Thay đổi IP này nếu IP máy tính của bạn đổi sang số khác
    generate_ssl_certificate(server_ip="192.168.1.150")
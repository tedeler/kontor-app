"""Selbst signierte Testzertifikate für die Attrappen (nur 127.0.0.1/localhost, E-122).

Erzeugt mit ``cryptography`` ein Zertifikat samt Schlüssel in einem temporären Verzeichnis. Die App
vertraut ihm nur, wenn ``tls_ca_datei`` auf ``zertifikat`` zeigt.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import ssl
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestZertifikat:
    zertifikat: Path      # PEM, zugleich Vertrauensanker
    schluessel: Path      # PEM, privater Schlüssel (nur für die Attrappe)

    def server_kontext(self) -> ssl.SSLContext:
        k = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        k.load_cert_chain(str(self.zertifikat), str(self.schluessel))
        return k


def erzeuge_zertifikat(verzeichnis: Path, name: str = "attrappe") -> TestZertifikat:
    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec  # noqa: PLC0415
    from cryptography.x509.oid import NameOID  # noqa: PLC0415

    verzeichnis.mkdir(parents=True, exist_ok=True)
    schluessel = ec.generate_private_key(ec.SECP256R1())
    subjekt = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kontor Test-Attrappe (synthetisch)")])
    jetzt = dt.datetime.now(dt.timezone.utc)
    zert = (x509.CertificateBuilder().subject_name(subjekt).issuer_name(subjekt)
            .public_key(schluessel.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(jetzt - dt.timedelta(days=1)).not_valid_after(jetzt + dt.timedelta(days=7))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                           critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(schluessel, hashes.SHA256()))
    z = verzeichnis / f"{name}.crt"
    s = verzeichnis / f"{name}.key"
    z.write_bytes(zert.public_bytes(serialization.Encoding.PEM))
    s.write_bytes(schluessel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    s.chmod(0o600)
    return TestZertifikat(z, s)

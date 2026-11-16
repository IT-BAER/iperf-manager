# -*- coding: utf-8 -*-
"""Self-signed EC P-256 certificate with the standard library only.

Used when no openssl CLI exists (Windows without Git for Windows). Trust comes from the
dashboard's fingerprint pin, not from a CA. The scalar multiplication is not constant
time; it runs once, when the agent creates its certificate.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import secrets

# NIST P-256 (FIPS 186-4, D.1.2.3)
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

_OID_EC_PUBLIC_KEY = bytes.fromhex('06072A8648CE3D0201')
_OID_PRIME256V1 = bytes.fromhex('06082A8648CE3D030107')
_OID_ECDSA_SHA256 = bytes.fromhex('06082A8648CE3D040302')
_OID_COMMON_NAME = bytes.fromhex('0603550403')


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    return x3, (lam * (x1 - x3) - y1) % _P


def _mul(k, point=_G):
    result = None
    for bit in bin(k)[2:]:
        result = _add(result, result)
        if bit == '1':
            result = _add(result, point)
    return result


def _sign(d: int, message: bytes) -> tuple[int, int]:
    z = int.from_bytes(hashlib.sha256(message).digest(), 'big')
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r = _mul(k)[0] % _N
        s = pow(k, -1, _N) * (z + r * d) % _N
        if r and s:
            return r, s


def _tlv(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + body


def _seq(*parts: bytes) -> bytes:
    return _tlv(0x30, b''.join(parts))


def _int(value: int) -> bytes:
    return _tlv(0x02, value.to_bytes(value.bit_length() // 8 + 1, 'big'))


def _time(when: datetime.datetime) -> bytes:
    # RFC 5280 4.1.2.5: UTCTime through 2049, GeneralizedTime from 2050.
    if when.year < 2050:
        return _tlv(0x17, when.strftime('%y%m%d%H%M%SZ').encode('ascii'))
    return _tlv(0x18, when.strftime('%Y%m%d%H%M%SZ').encode('ascii'))


def _pem(label: str, der: bytes) -> bytes:
    b64 = base64.b64encode(der).decode('ascii')
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return ('\n'.join([f'-----BEGIN {label}-----', *lines, f'-----END {label}-----']) + '\n').encode('ascii')


def generate_self_signed(common_name: str, days: int = 3650) -> tuple[bytes, bytes]:
    """Return (certificate PEM, SEC1 private key PEM) for a new P-256 key."""
    d = secrets.randbelow(_N - 1) + 1
    qx, qy = _mul(d)
    name = _seq(_tlv(0x31, _seq(_OID_COMMON_NAME, _tlv(0x0C, common_name.encode('utf-8')))))
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    algorithm = _seq(_OID_ECDSA_SHA256)
    spki = _seq(_seq(_OID_EC_PUBLIC_KEY, _OID_PRIME256V1),
                _tlv(0x03, b'\x00\x04' + qx.to_bytes(32, 'big') + qy.to_bytes(32, 'big')))
    tbs = _seq(
        _tlv(0xA0, _int(2)),  # X.509 v3
        _int(secrets.randbits(127) | 1 << 126),  # positive, at most 16 bytes
        algorithm,
        name,
        _seq(_time(now), _time(now + datetime.timedelta(days=days))),
        name,
        spki,
    )
    r, s = _sign(d, tbs)
    cert = _seq(tbs, algorithm, _tlv(0x03, b'\x00' + _seq(_int(r), _int(s))))
    # The public key is left out: OpenSSL derives it from d, so a wrong point in the
    # certificate shows up as a key mismatch when the agent loads the pair.
    key = _seq(_int(1), _tlv(0x04, d.to_bytes(32, 'big')), _tlv(0xA0, _OID_PRIME256V1))
    return _pem('CERTIFICATE', cert), _pem('EC PRIVATE KEY', key)

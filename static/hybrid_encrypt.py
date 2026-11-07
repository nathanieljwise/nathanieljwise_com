#!/usr/bin/env python3
"""Hybrid file encryption.

Recipient key type selects the path:
  RSA public key   -> RSA-OAEP(SHA-384) wraps a DEK        (format version 2)
  P-384 public key -> ECDH + HKDF-SHA384 KEK wraps a DEK   (format version 1)
The message is always encrypted with AES-256-GCM under the DEK.

Only dependency: cryptography
"""

import argparse
import os
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION_ECC = b"\x01"
VERSION_RSA = b"\x02"

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
P384_POINT_LEN = 97  # uncompressed X9.62 point
WRAPPED_DEK_LEN = KEY_LEN + TAG_LEN
MIN_RSA_BITS = 3072
MAX_MESSAGE_BYTES = 1 << 30

ECC_LABEL = b"hybrid-enc/v1/p384-ecdh-hkdf-sha384-aes256gcm"
RSA_LABEL = b"hybrid-enc/v2/rsa-oaep-sha384-aes256gcm"


class DecryptionError(Exception):
    pass


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def write_file(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def load_dek(path):
    """DEK file holds 32 raw bytes or 64 hex characters."""
    raw = read_file(path)
    if len(raw) == KEY_LEN:
        return raw
    try:
        key = bytes.fromhex(raw.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError):
        key = b""
    if len(key) != KEY_LEN:
        raise ValueError("DEK file must contain 32 raw bytes or 64 hex characters")
    return key


def is_p384_public(key):
    return isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == "secp384r1"


def is_p384_private(key):
    return isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == "secp384r1"


def point_bytes(public_key):
    return public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def oaep():
    return padding.OAEP(
        mgf=padding.MGF1(hashes.SHA384()), algorithm=hashes.SHA384(), label=RSA_LABEL
    )


def derive_kek(shared_secret, enc, recipient_point):
    # Context (suite label, version, ephemeral key, recipient key) is bound into info.
    info = ECC_LABEL + VERSION_ECC + enc + recipient_point
    return HKDF(
        algorithm=hashes.SHA384(), length=KEY_LEN, salt=None, info=info
    ).derive(shared_secret)


def encrypt(recipient_pub, plaintext, dek, context):
    msg_nonce = os.urandom(NONCE_LEN)

    if isinstance(recipient_pub, rsa.RSAPublicKey):
        if recipient_pub.key_size < MIN_RSA_BITS:
            raise ValueError(f"RSA key must be at least {MIN_RSA_BITS} bits")
        wrapped = recipient_pub.encrypt(dek, oaep())
        msg_aad = VERSION_RSA + wrapped + context
        ct = AESGCM(dek).encrypt(msg_nonce, plaintext, msg_aad)
        return VERSION_RSA + wrapped + msg_nonce + ct

    if is_p384_public(recipient_pub):
        eph = ec.generate_private_key(ec.SECP384R1())
        enc = point_bytes(eph.public_key())
        pk_r = point_bytes(recipient_pub)
        shared = eph.exchange(ec.ECDH(), recipient_pub)
        kek = derive_kek(shared, enc, pk_r)

        wrap_nonce = os.urandom(NONCE_LEN)
        wrapped = AESGCM(kek).encrypt(wrap_nonce, dek, VERSION_ECC + enc + pk_r)
        msg_aad = VERSION_ECC + enc + wrapped + context
        ct = AESGCM(dek).encrypt(msg_nonce, plaintext, msg_aad)
        return VERSION_ECC + enc + wrap_nonce + wrapped + msg_nonce + ct

    raise ValueError("Unsupported recipient key: need an RSA or P-384 public key")


def decrypt(private_key, blob, context):
    if not blob:
        raise DecryptionError
    version, body = blob[:1], blob[1:]

    if version == VERSION_RSA and isinstance(private_key, rsa.RSAPrivateKey):
        wrapped_len = private_key.key_size // 8
        if len(body) < wrapped_len + NONCE_LEN + TAG_LEN:
            raise DecryptionError
        wrapped = body[:wrapped_len]
        msg_nonce = body[wrapped_len : wrapped_len + NONCE_LEN]
        ct = body[wrapped_len + NONCE_LEN :]
        dek = private_key.decrypt(wrapped, oaep())
        return AESGCM(dek).decrypt(msg_nonce, ct, VERSION_RSA + wrapped + context)

    if version == VERSION_ECC and is_p384_private(private_key):
        fixed = P384_POINT_LEN + NONCE_LEN + WRAPPED_DEK_LEN + NONCE_LEN
        if len(body) < fixed + TAG_LEN:
            raise DecryptionError
        i = 0
        enc = body[i : i + P384_POINT_LEN]
        i += P384_POINT_LEN
        wrap_nonce = body[i : i + NONCE_LEN]
        i += NONCE_LEN
        wrapped = body[i : i + WRAPPED_DEK_LEN]
        i += WRAPPED_DEK_LEN
        msg_nonce = body[i : i + NONCE_LEN]
        i += NONCE_LEN
        ct = body[i:]

        # from_encoded_point validates that the point is on the curve
        eph_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP384R1(), enc)
        pk_r = point_bytes(private_key.public_key())
        shared = private_key.exchange(ec.ECDH(), eph_pub)
        kek = derive_kek(shared, enc, pk_r)

        dek = AESGCM(kek).decrypt(wrap_nonce, wrapped, VERSION_ECC + enc + pk_r)
        return AESGCM(dek).decrypt(
            msg_nonce, ct, VERSION_ECC + enc + wrapped + context
        )

    raise DecryptionError


def cmd_encrypt(args):
    if args.dek_file and args.dek_out_file:
        raise ValueError("--dek-out-file cannot be used together with --dek-file")
    if os.path.getsize(args.message_file) > MAX_MESSAGE_BYTES:
        raise ValueError("message exceeds 1 GiB limit")

    recipient_pub = serialization.load_pem_public_key(read_file(args.recipient_public_key_file))
    plaintext = read_file(args.message_file)

    dek = load_dek(args.dek_file) if args.dek_file else os.urandom(KEY_LEN)
    if args.dek_out_file:
        write_file(args.dek_out_file, dek.hex().encode("ascii") + b"\n")

    blob = encrypt(recipient_pub, plaintext, dek, args.context.encode("utf-8"))
    write_file(args.output_file, blob)


def cmd_decrypt(args):
    password = None
    if args.passphrase_file:
        password = read_file(args.passphrase_file).rstrip(b"\r\n")
    private_key = serialization.load_pem_private_key(
        read_file(args.private_key_file), password=password
    )
    plaintext = decrypt(private_key, read_file(args.input_file), args.context.encode("utf-8"))
    write_file(args.output_file, plaintext)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hybrid_crypt.py",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Hybrid file encryption: AES-256-GCM for the message, with the "
            "data encryption key (DEK) wrapped for the recipient.\n"
            "\n"
            "The recipient's public key type selects the path:\n"
            "\tRSA (3072+ bits)  RSA-OAEP wraps the DEK\n"
            "\tP-384 EC          ephemeral ECDH + HKDF-SHA384 wraps the DEK\n"
            "\n"
            "Keys are PEM files. No sender authentication is provided."
        ),
        epilog="Use 'hybrid_crypt.py <command> --help' for command details.",
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        metavar="{encrypt,decrypt}",
    )

    enc = sub.add_parser(
        "encrypt",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="encrypt a file for a recipient public key",
        description=(
            "Encrypt a file for a recipient. A random DEK is generated (or "
            "read from --dek), the message is encrypted with it, and the "
            "DEK is wrapped using the path matching the recipient's key type."
        ),
        epilog=(
            "example:\n"
            "  python hybrid_crypt.py encrypt --pubkey ec_pub.pem \\\n"
            "      --infile secret.txt --outfile secret.enc"
        ),
    )
    enc.add_argument(
        "--pubkey",
        dest="recipient_public_key_file",
        required=True,
        metavar="PATH",
        help="recipient PEM public key: RSA (3072+ bits) or P-384 EC",
    )
    enc.add_argument(
        "--infile",
        dest="message_file",
        required=True,
        metavar="PATH",
        help="file to encrypt (1 GiB maximum)",
    )
    enc.add_argument(
        "--outfile",
        dest="output_file",
        required=True,
        metavar="PATH",
        help="where to write the encrypted file",
    )
    enc.add_argument(
        "--dek",
        dest="dek_file",
        default=None,
        metavar="PATH",
        help="optional DEK: 32 raw bytes or 64 hex characters (default: generate one)",
    )
    enc.add_argument(
        "--dek-out",
        dest="dek_out_file",
        default=None,
        metavar="PATH",
        help="save the generated DEK as hex; protect it, it can decrypt the message",
    )
    enc.add_argument(
        "--context",
        default="",
        metavar="TEXT",
        help="optional non-secret label bound into the message; must match on decrypt",
    )
    enc.set_defaults(func=cmd_encrypt)

    dec = sub.add_parser(
        "decrypt",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="decrypt a file with the recipient private key",
        description=(
            "Decrypt a file made by 'encrypt'. The path is chosen from the "
            "file's version byte and the private key must match its type. "
            "All failures give the same generic error."
        ),
        epilog=(
            "example:\n"
            "  python hybrid_crypt.py decrypt --privkey ec_priv.pem \\\n"
            "      --infile secret.enc --outfile secret.out"
        ),
    )
    dec.add_argument(
        "--privkey",
        dest="private_key_file",
        required=True,
        metavar="PATH",
        help="recipient PEM private key (RSA or P-384 EC)",
    )
    dec.add_argument(
        "--passphrase",
        dest="passphrase_file",
        default=None,
        metavar="PATH",
        help="file holding the private key passphrase, if the key is encrypted",
    )
    dec.add_argument(
        "--infile",
        dest="input_file",
        required=True,
        metavar="PATH",
        help="encrypted file produced by 'encrypt'",
    )
    dec.add_argument(
        "--outfile",
        dest="output_file",
        required=True,
        metavar="PATH",
        help="where to write the plaintext",
    )
    dec.add_argument(
        "--context",
        default="",
        metavar="TEXT",
        help="context string used at encryption time (default: empty)",
    )
    dec.set_defaults(func=cmd_decrypt)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except Exception as exc:
        if args.command == "decrypt":
            # Deliberately uniform: no detail about why decryption failed.
            print("error: decryption failed", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Keys

This file lists the public keys and the encryption script published at https://nathanieljwise.com/publickeys. It lives on GitHub, a separate system from the web server, so you can compare the two before relying on a key.

## Current fingerprints

A key fingerprint is the SHA-256 of the key's DER SubjectPublicKeyInfo encoding. The script hash is the SHA-256 of the file's bytes.

```
ECC (P-384):  659e6494f682d9e7669ad20abd2907bee5a06674e97eabbdfa06f2d22dd8c192
RSA (4096):   a98270aec7ff8c17f9798f9f37d34a263c9e85701ff54961139d82aff66abfe2
hybrid_encrypt.py: 28a402f949fd717e33061d9bd424783e9b8e5430fd6863e53e119cfb31d4a1e0
```

## Details

- ECC key: P-384, `static/njwise_ecc_publicKey.pem`, created 2026-11-07. Preferred.
- RSA key: 4096-bit, `static/njwise_rsa_publicKey.pem`, created 2026-11-07. For compatibility.
- Script: `static/hybrid_encrypt.py`. The hash above is current as of 2026-11-07.
- Both keys are for encryption only. No expiry date is set; see Rotation below.

## How to verify

Check a key:

```
openssl pkey -pubin -in njwise_ecc_publicKey.pem -outform DER -out key.der
openssl dgst -sha256 key.der
```

On Windows PowerShell you can use `Get-FileHash key.der` for the second step.

Check the script:

```
sha256sum hybrid_encrypt.py
```

On Windows PowerShell: `Get-FileHash .\hybrid_encrypt.py`.

Compare each result with this file and with the values on the website. If any of them differ, do not use the key or the script, and contact me by another route.

## Key history

- 2026-11-07: current ECC and RSA keys created. Earlier keys retired.

Retired keys. Please do not encrypt to these:
```
ECC (P-384):  7bba320c9c60220ceca716140e1d9cc1a606c0d86a26180d79a0462925e2928d
RSA (4096):   bd7a665e083cf7eab6ec26e3b0d190aa12363eb4ecf1ed4cbb423939f394e4d9
```

## Rotation

Keys are replaced immediately if a private key may have been exposed, and reviewed at least once a year. Every change is recorded here and in this repository's commit history.

Messages are not forward secret. Anyone who later obtains a private key can decrypt past messages that were encrypted to it, and rotation limits how much that would expose.

## Limits

The scheme does not authenticate the sender, so anyone can create a valid message. Email subjects, filenames and timestamps are not encrypted.

## Contact

nathanieljwise@protonmail.com
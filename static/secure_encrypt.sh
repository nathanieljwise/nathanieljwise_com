#!/usr/bin/env bash
#
# Hybrid encryption: AES-256-CBC + RSA-OAEP key wrap + RSA signature (sign-then-verify-before-decrypt).
#
# Note: openssl's `enc` CLI does not support AEAD ciphers (GCM) despite the
# library supporting it, so we use CBC and get integrity/authenticity from
# signing the *entire* envelope (IV + ciphertext + wrapped key) and verifying
# that signature BEFORE any decryption is attempted. This closes the gap in
# the original script, which signed only the wrapped key and left the
# ciphertext unauthenticated.
#
# Envelope format written to <file>.enc:
#   [16-byte IV][ciphertext]
#
# Usage:
#   ./secure_encrypt.sh encrypt <infile> <pubkey.pem> <privkey.pem>
#   ./secure_encrypt.sh decrypt <infile.enc> <privkey.pem> <pubkey.pem>

set -euo pipefail
set +o history 2>/dev/null || true

if [[ $# -ne 4 || ( "$1" != "encrypt" && "$1" != "decrypt" ) ]]; then
  echo "Incorrect usage. Expected:"
  echo "  $0 encrypt <infile> <pubkey.pem> <privkey.pem>"
  echo "  $0 decrypt <infile.enc> <privkey.pem> <pubkey.pem>"
  exit 1
fi

mode="${1:?mode: encrypt|decrypt}"
infile="${2:?input file}"
key1="${3:?key1}"
key2="${4:?key2}"

encrypt() {
  local plaintext="$infile" pubkey="$key1" privkey="$key2"
  local base out
  base="$(basename "$plaintext")"
  out="${base}.enc"

  local iv aes_key
  iv="$(openssl rand -hex 16)"
  aes_key="$(openssl rand -hex 32)"

  # Encrypt; prepend IV to the ciphertext file so it travels with the data.
  openssl enc -aes-256-cbc -K "$aes_key" -iv "$iv" -in "$plaintext" -out "${out}.body"
  { printf '%s' "$iv" | xxd -r -p; cat "${out}.body"; } > "$out"
  rm -f "${out}.body"

  # Wrap the AES key under RSA-OAEP.
  printf '%s' "$aes_key" | xxd -r -p | \
    openssl pkeyutl -encrypt -pubin -inkey "$pubkey" \
      -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256 \
      -out "${base}.key.enc"

  # Sign ciphertext-envelope + wrapped key TOGETHER, so tampering with
  # either the message or the key blob invalidates the signature.
  cat "$out" "${base}.key.enc" > "${base}.envelope.tmp"
  openssl dgst -sha256 -sign "$privkey" -out "${base}.sig" "${base}.envelope.tmp"
  rm -f "${base}.envelope.tmp"

  unset aes_key
  echo "Wrote: $out, ${base}.key.enc, ${base}.sig"
}

decrypt() {
  local ciphertext="$infile" privkey="$key1" pubkey="$key2"
  local base out
  base="${ciphertext%.enc}"
  out="${base}.dec"

  # Verify signature over the full envelope BEFORE decrypting anything.
  cat "$ciphertext" "${base}.key.enc" > "${base}.envelope.tmp"
  if ! openssl dgst -sha256 -verify "$pubkey" -signature "${base}.sig" "${base}.envelope.tmp"; then
    rm -f "${base}.envelope.tmp"
    echo "Signature verification FAILED — refusing to decrypt." >&2
    exit 1
  fi
  rm -f "${base}.envelope.tmp"

  # Unwrap AES key.
  local aes_key
  aes_key="$(openssl pkeyutl -decrypt -inkey "$privkey" \
    -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256 \
    -in "${base}.key.enc" | xxd -p -c 256)"

  # Split IV (first 16 bytes) from ciphertext body.
  local iv
  iv="$(head -c 16 "$ciphertext" | xxd -p -c 16)"
  tail -c +17 "$ciphertext" > "${ciphertext}.body"

  openssl enc -d -aes-256-cbc -K "$aes_key" -iv "$iv" -in "${ciphertext}.body" -out "$out"
  rm -f "${ciphertext}.body"
  unset aes_key

  echo "Decrypted to: $out"
}

case "$mode" in
  encrypt) encrypt ;;
  decrypt) decrypt ;;
  *) echo "mode must be 'encrypt' or 'decrypt'" >&2; exit 1 ;;
esac
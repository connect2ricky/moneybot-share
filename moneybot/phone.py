"""An encrypted copy of the dashboard's data for the phone app, kept on its own branch of the private backup repository.

File layout: b"MBP1" + 12-byte nonce + AES-256-GCM(gzip(JSON)). The key is 32 random bytes, so unlike the backup
passphrase it needs no stretching, and the phone holds a key that opens this file but not the full backups.
The branch is one commit, replaced on each publish, so the repository does not grow.
"""
import base64
import gzip
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .backup import BackupError, _git
from .config import BACKUP_DIR, BACKUP_REPO

MAGIC = b"MBP1"
BRANCH = "phone"
FILE_NAME = "moneybot.mbp"
KEYCHAIN_SERVICE = "moneybot-phone"
TOKEN_SERVICE = "moneybot-phone-token"
_published = None


def encrypt(data: bytes, key: str) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(base64.urlsafe_b64decode(key)).encrypt(nonce, gzip.compress(data), MAGIC)


def saved_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"], capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def key() -> str:
    """The key the phone app needs, created on first use."""
    found = saved_key()
    if found:
        return found
    value = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    command = f'add-generic-password -U -s {KEYCHAIN_SERVICE} -a moneybot -w "{value}"\n'
    subprocess.run(["security", "-i"], input=command, capture_output=True, text=True)
    if saved_key() != value:
        raise BackupError("Could not save the phone key to the macOS Keychain.")
    return value


def save_token(token: str):
    """Keep the phone's read-only GitHub token for personal builds, once GitHub confirms it can read the file."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{BACKUP_REPO}/contents/{FILE_NAME}?ref={BRANCH}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"},
    )
    try:
        urllib.request.urlopen(request, timeout=30).read()
    except urllib.error.URLError as exc:
        raise BackupError(f"GitHub did not accept this token for {BACKUP_REPO}: {exc}") from None
    command = f'add-generic-password -U -s {TOKEN_SERVICE} -a moneybot -w "{token}"\n'
    subprocess.run(["security", "-i"], input=command, capture_output=True, text=True, check=True)


def publish(data: dict) -> bool:
    """Push the data for the phone. False when nothing changed, or the phone has not been set up."""
    global _published
    phone_key = saved_key()
    if not phone_key:
        return False
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).digest()
    if digest == _published:
        return False
    if not (BACKUP_DIR / ".git").exists():
        raise BackupError(f"The backup folder {BACKUP_DIR} is not set up.")
    payload = json.dumps({**data, "published_ts": int(time.time())}).encode()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / FILE_NAME
        path.write_bytes(encrypt(payload, phone_key))
        blob = _git("hash-object", "-w", str(path)).stdout.strip()
    tree = _git("mktree", input=f"100644 blob {blob}\t{FILE_NAME}\n").stdout.strip()
    commit = _git("-c", "user.name=moneybot", "-c", "user.email=moneybot@localhost",
                  "commit-tree", tree, "-m", "Latest data for the phone app").stdout.strip()
    _git("push", "-q", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
    _published = digest
    return True

"""Encrypted backups of the whole database, kept in a separate private GitHub repository.

File layout: b"MBK1" + 16-byte salt + 12-byte nonce + AES-256-GCM(gzip(database)).
The key is derived from the passphrase with scrypt, so the file is useless without it.
"""
import getpass
import gzip
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .config import BACKUP_DIR, BACKUP_GH_USER, BACKUP_REPO, DB_FILE

MAGIC = b"MBK1"
KEYCHAIN_SERVICE = "moneybot-backup"
ENV_VAR = "MONEYBOT_BACKUP_PASSPHRASE"


class BackupError(Exception):
    pass


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def encrypt(data: bytes, passphrase: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_key(passphrase, salt)).encrypt(nonce, gzip.compress(data), MAGIC)


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if blob[:4] != MAGIC:
        raise BackupError("This is not a moneybot backup file.")
    salt, nonce, body = blob[4:20], blob[20:32], blob[32:]
    try:
        return gzip.decompress(AESGCM(_key(passphrase, salt)).decrypt(nonce, body, MAGIC))
    except InvalidTag:
        raise BackupError("Wrong passphrase, or the backup file is damaged.") from None


def _keychain_get():
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"], capture_output=True, text=True
    )
    return result.stdout.rstrip("\n") if result.returncode == 0 and result.stdout.strip() else None


def _keychain_set(passphrase: str):
    # Sent on stdin so the passphrase never appears in the process list.
    quoted = passphrase.replace("\\", "\\\\").replace('"', '\\"')
    command = f'add-generic-password -U -s {KEYCHAIN_SERVICE} -a moneybot -w "{quoted}"\n'
    result = subprocess.run(["security", "-i"], input=command, capture_output=True, text=True)
    if result.returncode != 0 or _keychain_get() != passphrase:
        raise BackupError("Could not save the passphrase to the macOS Keychain.")


def passphrase(create: bool, interactive: bool = True) -> str:
    """From the environment, then the Keychain, then by asking. A new one is asked for twice and saved."""
    found = os.environ.get(ENV_VAR) or _keychain_get()
    if found:
        return found
    if not interactive:
        raise BackupError("No backup passphrase is saved yet. Run `uv run moneybot backup` once in a terminal to choose one.")
    if not create:
        return getpass.getpass("Backup passphrase: ")
    print("Choose a passphrase for your backups. Without it a backup cannot be opened, by anyone.")
    first = getpass.getpass("Passphrase (8 characters or more): ")
    if len(first) < 8:
        raise BackupError("The passphrase needs at least 8 characters.")
    if getpass.getpass("Type it again: ") != first:
        raise BackupError("The two passphrases did not match.")
    _keychain_set(first)
    print("Saved to the macOS Keychain, so later backups will not ask. Keep your own copy somewhere safe too.")
    return first


def snapshot() -> bytes:
    """A consistent copy of the live database, even while the dashboard has it open."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "copy.db"
        source, dest = sqlite3.connect(DB_FILE), sqlite3.connect(target)
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
        return target.read_bytes()


def _git(*args, check=True, input=None):
    # Pushes authenticate as the backup repository's owner whichever GitHub account is active.
    helper = f"!GH_TOKEN=$(gh auth token --user {BACKUP_GH_USER}) gh auth git-credential"
    result = subprocess.run(
        ["git", "-C", str(BACKUP_DIR), "-c", "credential.helper=", "-c", f"credential.helper={helper}", *args],
        capture_output=True, text=True, input=input,
    )
    if check and result.returncode != 0:
        raise BackupError(f"git {args[0]} failed: {(result.stderr or result.stdout).strip()[:300]}")
    return result


def make(push: bool = True, interactive: bool = True) -> dict:
    if not BACKUP_REPO:
        raise BackupError("Backups are off. Set BACKUP_REPO and BACKUP_GH_USER in moneybot/config.py (see README.md).")
    if not (BACKUP_DIR / ".git").exists():
        raise BackupError(f"The backup folder {BACKUP_DIR} is not set up. It should be a clone of {BACKUP_REPO}.")
    data = snapshot()
    blob = encrypt(data, passphrase(create=True, interactive=interactive))
    name = f"moneybot-{datetime.now():%Y-%m-%d}.mbk"
    (BACKUP_DIR / name).write_bytes(blob)
    _git("add", name)
    if _git("status", "--porcelain").stdout.strip():
        _git("-c", "user.name=moneybot", "-c", "user.email=moneybot@localhost",
             "commit", "-q", "-m", f"Backup {datetime.now():%Y-%m-%d %H:%M}")
    pushed = False
    if push:
        pushed = _git("push", "-q", "origin", "HEAD", check=False).returncode == 0
    return {"file": name, "bytes": len(blob), "database_bytes": len(data), "pushed": pushed}


def restore(source: Path, out: Path) -> Path:
    """Decrypt a backup into a new file. The live database is never overwritten."""
    if out.exists():
        raise BackupError(f"{out} already exists; choose another name.")
    data = decrypt(Path(source).read_bytes(), passphrase(create=False))
    out.write_bytes(data)
    check = sqlite3.connect(out)
    tables = check.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    check.close()
    if not tables:
        raise BackupError("The backup decrypted but does not contain a database.")
    return out

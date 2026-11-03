"""Admin commands for the venue install. Added by the Tranquil Turtle fork.

  python manage.py create-admin "Name" login
  python manage.py import-baseline stocktake.xlsx
  python manage.py import-catalogue square-catalogue.csv
  python manage.py backup [folder]
  python manage.py export-data bundle.txt      (password in OSB_BUNDLE_PASSWORD)
  python manage.py import-data bundle.txt      (password in OSB_BUNDLE_PASSWORD)
"""

from __future__ import annotations

import getpass
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("OSB_DATA_DIR") or os.path.join(_DIR, "data")
KEEP_BACKUPS = 30


def backup(dest: str = "") -> str:
    """Zip the whole data folder. SQLite is copied through its backup API so a live server is safe."""
    dest = dest or os.path.join(_DIR, "backups")
    os.makedirs(dest, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "data")
        shutil.copytree(DATA, copy, ignore=shutil.ignore_patterns("venue.sqlite*", "_backups", "*.tmp"))
        src_path = os.path.join(DATA, "venue.sqlite")
        if os.path.exists(src_path):
            src, out = sqlite3.connect(src_path), sqlite3.connect(os.path.join(copy, "venue.sqlite"))
            with out:
                src.backup(out)
            src.close()
            out.close()
        made = shutil.make_archive(os.path.join(dest, f"venue-data-{stamp}"), "zip", copy)
    old = sorted(f for f in os.listdir(dest) if f.startswith("venue-data-") and f.endswith(".zip"))
    for name in old[:-KEEP_BACKUPS]:
        os.remove(os.path.join(dest, name))
    return made


def _bundle_key(password: str, salt: bytes) -> bytes:
    import base64
    import hashlib

    return base64.urlsafe_b64encode(hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=2**26, dklen=32))


def _strip_machine_files(raw: bytes) -> bytes:
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name not in ("session_secret.txt", "login_throttle.json", "setup_token.txt"):
                dst.writestr(name, src.read(name))
    return out.getvalue()


def export_data(path: str, password: str) -> None:
    """Encrypt the stock data for moving to another PC. Logins come too; the session secret does not."""
    import base64

    from cryptography.fernet import Fernet

    with tempfile.TemporaryDirectory() as tmp:
        with open(backup(tmp), "rb") as fh:
            raw = _strip_machine_files(fh.read())
    salt = os.urandom(16)
    token = Fernet(_bundle_key(password, salt)).encrypt(raw)
    with open(path, "w", encoding="ascii") as fh:
        fh.write(base64.b64encode(salt).decode() + ":" + token.decode())


def import_data(path: str, password: str) -> int:
    """Restore a bundle. Refuses to touch a PC that already has stock data."""
    import base64
    import io
    import zipfile

    from cryptography.fernet import Fernet, InvalidToken

    if os.path.exists(os.path.join(DATA, "venue.sqlite")):
        print("Stock data already exists here, so nothing was changed.")
        return 3
    with open(path, encoding="ascii") as fh:
        salt, token = fh.read().strip().split(":", 1)
    try:
        raw = Fernet(_bundle_key(password, base64.b64decode(salt))).decrypt(token.encode())
    except InvalidToken:
        print("Wrong password")
        return 4
    os.makedirs(DATA, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(DATA)
    print("Stock data restored")
    return 0


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "backup":
        print(backup(args[1] if len(args) > 1 else ""))
        return 0
    if cmd in ("export-data", "import-data") and len(args) == 2:
        password = os.environ.get("OSB_BUNDLE_PASSWORD", "")
        if not password:
            print("Set OSB_BUNDLE_PASSWORD first")
            return 1
        if cmd == "import-data":
            return import_data(args[1], password)
        export_data(args[1], password)
        print(args[1])
        return 0
    if cmd == "import-baseline" and len(args) == 2:
        import venue_db as db
        import venue_import

        conn = db.connect(DATA)
        with conn:
            print(venue_import.import_baseline(conn, args[1]))
        return 0
    if cmd == "import-catalogue" and len(args) == 2:
        import venue_db as db
        import venue_import

        conn = db.connect(DATA)
        with conn, open(args[1], "rb") as fh:
            print(venue_import.import_catalogue(conn, venue_import.decode_export(fh.read())))
        return 0
    if cmd == "create-admin" and len(args) == 3:
        import server

        people = server._load_people()
        if server._find_user(people, login=args[2]):
            print("That login already exists")
            return 1
        pin = os.environ.get("OSB_NEW_PIN") or getpass.getpass("6-digit PIN: ")
        if not server._valid_pin(pin):
            print("PIN must be exactly 6 digits")
            return 1
        people["users"].append({
            "id": server._uid("user-"), "name": args[1], "login": args[2], "role": "admin", "venue_id": None,
            "pin_hash": server._hash_pin(pin), "permissions": dict(server.ADMIN_PERMISSIONS), "active": True,
            "created_at": server._now(), "updated_at": server._now(),
        })
        server._save_people(people)
        print(f"Admin {args[1]} created")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Create a ready-to-run .env with fresh random secrets and demo mode switched on.

    python scripts/init_env.py            # writes .env (refuses to overwrite one)
    python scripts/init_env.py --force    # overwrite

Needs only Python 3 (no packages). The values in .env.example are placeholders; this
fills in a random database password and signing key so nothing predictable is used.
"""

import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def main() -> int:
    if TARGET.exists() and "--force" not in sys.argv:
        print(".env already exists, leaving it alone. Use --force to overwrite.")
        return 1

    text = TEMPLATE.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^POSTGRES_PASSWORD=.*$", f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}", text)
    text = re.sub(r"(?m)^SECRET_KEY=.*$", f"SECRET_KEY={secrets.token_urlsafe(64)}", text)
    # Demo mode: sample Google data, so every screen works with no accounts or keys
    text = re.sub(r"(?m)^# GOOGLE_PROVIDER=demo", "GOOGLE_PROVIDER=demo", text)
    TARGET.write_text(text, encoding="utf-8", newline="\n")

    print("Created .env with random secrets and Google demo mode on.")
    print("Next:  docker compose up -d --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

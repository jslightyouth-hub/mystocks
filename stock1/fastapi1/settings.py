import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / "config" / ".env"


def _load_env_file():
    # Keep local secrets out of source files while still supporting simple .env setup.
    if not ENV_FILE.exists():
        return

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def get_required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Please configure {name} in config/.env")
    return value


TUSHARE_TOKEN = get_required_env("TUSHARE_TOKEN")
DATABASE_URL = get_required_env("DATABASE_URL")

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
OUT_LOG = ROOT / "sync_financial_mainbz.full.out.log"
ERR_LOG = ROOT / "sync_financial_mainbz.full.err.log"


def main():
    out_file = OUT_LOG.open("ab", buffering=0)
    err_file = ERR_LOG.open("ab", buffering=0)
    process = subprocess.Popen(
        [
            str(PYTHON),
            "-u",
            "sync_financial_mainbz.py",
            "--skip-synced",
            "--request-interval",
            "0.35",
        ],
        cwd=ROOT,
        stdout=out_file,
        stderr=err_file,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=False,
    )
    print(process.pid)


if __name__ == "__main__":
    main()

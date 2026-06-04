import sys

from sync_financials import main


if "--interfaces" not in sys.argv:
    sys.argv.extend(["--interfaces", "cashflow"])


if __name__ == "__main__":
    main()

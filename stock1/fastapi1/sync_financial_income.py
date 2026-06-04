import sys

from sync_financials import main


if "--interfaces" not in sys.argv:
    sys.argv.extend(["--interfaces", "income"])


if __name__ == "__main__":
    main()

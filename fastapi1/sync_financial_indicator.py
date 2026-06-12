import sys

from sync_financials import main


if "--interfaces" not in sys.argv:
    sys.argv.extend(["--interfaces", "fina_indicator"])


if __name__ == "__main__":
    main()

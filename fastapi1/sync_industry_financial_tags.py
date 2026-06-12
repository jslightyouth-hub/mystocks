import argparse

from industry_tag_service import sync_industry_financial_tags


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate financial tags by comparing stocks inside the same SW level-3 industry."
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Annual report period in YYYY1231 format. Default: latest five annual periods.",
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help="Only calculate one stock code, for example 600519.SH.",
    )
    parser.add_argument(
        "--sw-l3-code",
        default=None,
        help="Only calculate one SW level-3 industry code.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate tags and print counts without writing database rows.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = sync_industry_financial_tags(
        end_date=args.end_date,
        ts_code=args.ts_code,
        sw_l3_code=args.sw_l3_code,
        dry_run=args.dry_run,
    )
    print(
        "Done. "
        f"periods={','.join(result['periods']) if result['periods'] else 'none'} "
        f"tag_count={result['tag_count']} "
        f"dry_run={result['dry_run']}"
    )


if __name__ == "__main__":
    main()

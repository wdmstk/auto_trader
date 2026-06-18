"""CLI interface for execution reconciliation."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Execution reconciliation service")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        print("Execution Reconciliation Service v1.0")
        return 0

    # Default: show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

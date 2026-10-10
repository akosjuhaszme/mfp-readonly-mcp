import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="myfitnesspal-mcp",
        description="Read-only MCP server for MyFitnessPal (stdio only).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve", "auth"],
        default="serve",
        help="serve (default) or auth to connect your MyFitnessPal account",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="with auth: report whether the saved session works, without prompting",
    )
    args = parser.parse_args()

    if args.check and args.command != "auth":
        parser.error("--check only applies to the auth command")

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    if args.command == "auth" and args.check:
        from .auth import run_check

        raise SystemExit(run_check())

    if args.command == "auth":
        from .auth import run_auth_flow

        raise SystemExit(run_auth_flow())

    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()

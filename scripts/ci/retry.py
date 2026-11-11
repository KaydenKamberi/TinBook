"""Run a command, retrying it with a per-attempt timeout (used by the CI workflow).

Usage:
    python scripts/ci/retry.py --attempts 3 --timeout 600 --delay 20 -- python -m pip install -r requirements.txt

Exits with the last attempt's exit code (124 if it timed out).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retry a command with a timeout per attempt.")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600, help="seconds per attempt")
    parser.add_argument("--delay", type=float, default=15, help="seconds before the 2nd attempt (doubles)")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")

    code = 1
    delay = args.delay
    for attempt in range(1, args.attempts + 1):
        print(f"[retry] attempt {attempt}/{args.attempts} (timeout {args.timeout:.0f} s): {' '.join(command)}", flush=True)
        try:
            code = subprocess.run(command, timeout=args.timeout).returncode
        except subprocess.TimeoutExpired:
            print(f"[retry] attempt {attempt} timed out after {args.timeout:.0f} s", flush=True)
            code = 124
        if code == 0:
            return 0
        print(f"[retry] attempt {attempt} failed with exit code {code}", flush=True)
        if attempt < args.attempts:
            print(f"[retry] waiting {delay:.0f} s", flush=True)
            time.sleep(delay)
            delay *= 2
    return code


if __name__ == "__main__":
    sys.exit(main())

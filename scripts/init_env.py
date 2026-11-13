"""Create a .env from .env.example with fresh random secrets.

    uv run python scripts/init_env.py            # writes .env (refuses to overwrite)
    uv run python scripts/init_env.py --output other.env

Only the secret variables are generated; everything else keeps the example's value.
"""

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = {
    "DJANGO_SECRET_KEY": 40,
    "POSTGRES_PASSWORD": 20,
    "DB_OWNER_PASSWORD": 20,
    "DB_APP_PASSWORD": 20,
}


def build(example: str) -> str:
    lines = []
    for line in example.splitlines():
        name, _, value = line.partition("=")
        if name in SECRETS and not value:
            line = f"{name}={secrets.token_hex(SECRETS[name])}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    if args.output.exists():
        print(f"{args.output} already exists; not overwriting it.", file=sys.stderr)
        return 1
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(build(example))
    print(f"Wrote {args.output} with new random secrets. Keep it private.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

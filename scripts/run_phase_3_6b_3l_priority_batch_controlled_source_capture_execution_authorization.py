from __future__ import annotations

import argparse
import json
from pathlib import Path

from foundation.market.priority_batch_controlled_source_capture_execution_authorization import (
    write_authorization,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-plan", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    _, summary = write_authorization(
        Path(args.capture_plan),
        Path(args.policy),
        Path(args.output),
        Path(args.summary),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

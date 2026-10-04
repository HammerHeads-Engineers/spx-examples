"""Detached Setup worker: contains no terminal prompts or credential arguments."""

import argparse
import json
import os
from pathlib import Path
from .setup_session import SetupEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    environment = Path(args.state_root) / args.session_id / "execution-environment.json"
    if environment.is_file():
        os.environ.update(json.loads(environment.read_text(encoding="utf-8")))
    SetupEngine(Path(args.state_root)).run_job(args.session_id, args.job_id)


if __name__ == "__main__":
    main()

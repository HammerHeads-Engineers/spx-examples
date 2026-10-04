"""Detached Setup worker: contains no terminal prompts or credential arguments."""

import argparse
from pathlib import Path
from .setup_session import SetupEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    SetupEngine(Path(args.state_root)).run_job(args.session_id, args.job_id)


if __name__ == "__main__":
    main()

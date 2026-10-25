"""Run required release tests; a skipped or empty run cannot qualify a release."""

import sys

import pytest


class RequiredTests:
    """Record skips reported during collection, setup or test execution."""

    def __init__(self):
        self.skipped = 0

    def pytest_collectreport(self, report):
        if report.skipped:
            self.skipped += 1

    def pytest_runtest_logreport(self, report):
        if report.skipped:
            self.skipped += 1


def main(args=None):
    checks = RequiredTests()
    status = int(pytest.main(sys.argv[1:] if args is None else args, plugins=[checks]))
    if checks.skipped:
        print(f"Required tests were skipped: {checks.skipped}", file=sys.stderr)
        return status or 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())

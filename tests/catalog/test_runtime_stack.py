import subprocess

import pytest

from tools.runtime_stack import RuntimeStack, redact_log


def test_docker_fixtures_keep_the_key_out_of_arguments_and_redact_collected_logs(
    tmp_path, monkeypatch
):
    key = "private-fixture-key-123"
    monkeypatch.setenv("SPX_PRODUCT_KEY", key)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        stdout = (
            "127.0.0.1:18000"
            if args[1] == "port"
            else ("log " + key if args[1] == "logs" else "ok")
        )
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: type("Response", (), {"status_code": 200})(),
    )
    logs = tmp_path / "logs"
    with RuntimeStack(
        tmp_path, "simplephysx/spx-server:v1.0.0-rc.78@sha256:" + "a" * 64, logs
    ) as stack:
        assert stack.url == "http://127.0.0.1:18000"
    assert all(key not in " ".join(args) for args in calls)
    assert len([args for args in calls if args[1:3] == ["rm", "--force"]]) == 5
    # Matter writes as root on Linux; keep its state off the runner filesystem
    # and delete every fixture's anonymous volumes with the owned container.
    matter = next(args for args in calls if "matter-server" in args)
    assert "type=volume,target=/data" in matter
    removals = [args for args in calls if args[1:3] == ["rm", "--force"]]
    assert all("--volumes" in args for args in removals)
    assert all(args[-1].startswith(stack.prefix + "-") for args in removals)
    assert any(args[1:3] == ["network", "rm"] for args in calls)
    assert all(
        key not in path.read_text(encoding="utf-8") for path in logs.glob("*.log")
    )
    assert "[REDACTED]" in (logs / "server.log").read_text(encoding="utf-8")


def test_unpinned_server_image_is_rejected_before_starting_docker(tmp_path):
    with pytest.raises(ValueError, match="pinned"):
        RuntimeStack(tmp_path, "simplephysx/spx-server:latest", tmp_path / "logs")


def test_decoded_license_identity_is_not_uploaded_with_diagnostic_logs():
    text = "Decoded product key info:\nPlan Name: CO\nUsername: confidential-user\nUser confidential-user is using the COMMUNITY plan.\nLoading from directory: /app/extensions\nTraceback:\nTypeError: useful diagnostic\nprivate-token\n"
    clean = redact_log(text, "private-token")
    assert "confidential-user" not in clean
    assert "Plan Name" not in clean
    assert "private-token" not in clean
    assert "TypeError: useful diagnostic" in clean

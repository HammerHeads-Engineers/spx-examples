import yaml

from tools.check_docs import HISTORICAL, check_docs
from scripts.render_readme_catalog import render


def test_local_link_case_is_checked_even_on_windows(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/Guide.md").write_text("# Guide\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "[Guide](docs/Guide.md#section)\n[Web](https://example.invalid)\n",
        encoding="utf-8",
    )
    assert check_docs(tmp_path) == []
    readme.write_text("[Guide](docs/guide.md)\n", encoding="utf-8")
    assert any("incorrectly cased" in issue for issue in check_docs(tmp_path))


def test_reference_links_and_missing_repository_commands_are_checked(tmp_path):
    (tmp_path / "README.md").write_text(
        "[guide][ref]\n\n[ref]: docs/missing.md\n"
        "`poetry run python -m installer generate`\n"
        "`python examples/core/missing.py`\n",
        encoding="utf-8",
    )
    issues = check_docs(tmp_path)
    assert any("docs/missing.md" in issue for issue in issues)
    assert any("module: installer" in issue for issue in issues)
    assert any("script: examples/core/missing.py" in issue for issue in issues)


def test_history_keeps_old_commands_but_still_checks_its_links(tmp_path):
    (tmp_path / "README.md").write_text(
        HISTORICAL + "\n`python -m installer generate`\n[Source](gone.md)\n",
        encoding="utf-8",
    )
    issues = check_docs(tmp_path)
    assert len(issues) == 1 and "gone.md" in issues[0]


def test_complete_model_examples_are_checked_without_treating_fragments_as_models(
    tmp_path,
):
    readme = tmp_path / "README.md"
    readme.write_text("```yaml\nmeta_parameters: {}\n```\n", encoding="utf-8")
    assert check_docs(tmp_path) == []
    readme.write_text(
        "<!-- spx-model-example -->\n```yaml\nname: invalid_model\n```\n",
        encoding="utf-8",
    )
    assert any("attributes" in issue for issue in check_docs(tmp_path))


def test_generated_channel_counts_do_not_claim_release_qualification(tmp_path):
    catalog = tmp_path / "library/catalog"
    catalog.mkdir(parents=True)
    (catalog / "industries.yaml").write_text("industries: []\n", encoding="utf-8")
    models = [
        {"domain_group": "lab", "protocols": ["mqtt"]},
        {
            "domain_group": "lab",
            "protocols": ["ble"],
            "distribution": {"channels": ["preview"]},
        },
    ]
    (catalog / "models.yaml").write_text(
        yaml.safe_dump({"models": models}), encoding="utf-8"
    )
    output = render(tmp_path)
    assert "**2 preview / 1 stable**" in output
    assert "eligibility" in output and "release assets" in output

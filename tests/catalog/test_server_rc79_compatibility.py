"""Keep the installer catalog usable on the declared Server RCs."""

import pytest

from tools.model_catalog import ROOT, distribution_config, server_matches


@pytest.mark.parametrize("version", ["1.0.0-rc.78", "1.0.0-rc.79", "1.0.0-rc.80"])
def test_catalog_declares_installer_server_targets(version):
    config = distribution_config(ROOT)
    assert version in config["qualification_targets"]
    assert server_matches(config["server_compatibility"], version)


@pytest.mark.parametrize("version", ["1.0.0-rc.77", "1.0.0-rc.81", "1.0.0"])
def test_catalog_does_not_claim_unqualified_server_versions(version):
    config = distribution_config(ROOT)
    assert not server_matches(config["server_compatibility"], version)

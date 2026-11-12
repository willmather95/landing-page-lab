import pytest

from landing_page_lab.deploy import CloudflarePagesPreview, DeployRefused, VercelPreview
from landing_page_lab.site.build import build_site
from landing_page_lab.variants import generate_variants


@pytest.fixture()
def dist(brief, tmp_path):
    return build_site(brief, generate_variants(brief), tmp_path / "dist").dist


def test_vercel_dry_run_is_preview_only(dist):
    v = VercelPreview("lpl-demo", env={})
    res = v.deploy(dist, ["a", "b", "c"])
    assert res.dry_run and res.urls["b"].endswith("/b/")
    final = res.requests[-1]
    assert final["url"].endswith("/v13/deployments") and "target" not in final["json"]
    uploads = [r for r in res.requests if r["url"].endswith("/v2/files")]
    assert len(uploads) == len(final["json"]["files"]) == 7  # 3 pages + router + css + js + manifest
    assert all(r["headers"]["Authorization"] == "<redacted>" for r in res.requests)


def test_vercel_refuses_protected_projects_and_missing_token():
    with pytest.raises(DeployRefused, match="PROTECTED"):
        VercelPreview("my-real-site", env={"LPL_PROTECTED_PROJECTS": "other, my-real-site"})
    with pytest.raises(DeployRefused, match="VERCEL_TOKEN"):
        VercelPreview("lpl-demo", env={"LPL_DEPLOY_LIVE": "1"})


def test_cloudflare_dry_run_sequence(dist):
    cf = CloudflarePagesPreview("lpl-demo", "lpl-fieldnote", env={})
    res = cf.deploy(dist, ["a", "b", "c"])
    tails = [r["url"].rsplit("/", 1)[-1] for r in res.requests]
    assert tails == ["upload-token", "check-missing", "upload", "upsert-hashes", "deployments"]
    assert res.dry_run and res.urls["router"].startswith("https://")


@pytest.mark.parametrize("branch", ["main", "master", "production", "release"])
def test_cloudflare_refuses_production_branch(branch):
    with pytest.raises(DeployRefused, match="production"):
        CloudflarePagesPreview("lpl-demo", branch, production_branch="release", env={})


def test_cloudflare_live_needs_credentials():
    with pytest.raises(DeployRefused, match="CLOUDFLARE"):
        CloudflarePagesPreview("lpl-demo", "lpl-x", env={"LPL_DEPLOY_LIVE": "1"})


def test_deploy_requires_a_build(tmp_path):
    with pytest.raises(FileNotFoundError):
        VercelPreview("lpl-demo", env={}).deploy(tmp_path, ["a"])

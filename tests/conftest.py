from pathlib import Path

import pytest

from landing_page_lab.brief import load_brief

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / "examples" / "brief.yaml"


@pytest.fixture(scope="session")
def brief():
    return load_brief(BRIEF)


@pytest.fixture(scope="session")
def brief_path():
    return BRIEF

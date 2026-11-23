import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_sample_pdf import build  # noqa: E402


@pytest.fixture(scope="session")
def sample_pdf_bytes(tmp_path_factory) -> bytes:
    path = build(tmp_path_factory.mktemp("pdf") / "sample.pdf")
    return path.read_bytes()

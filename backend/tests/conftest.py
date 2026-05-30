from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="hvac-pytest-")
os.environ["HVAC_DATA_DIR"] = _tmp

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def minimal_pdf_path(tmp_path) -> str:
    import fitz

    p = tmp_path / "one_page.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(p)
    doc.close()
    return str(p)

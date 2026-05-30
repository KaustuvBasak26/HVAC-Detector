from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_upload_rejects_non_pdf(client):
    r = client.post(
        "/api/files/upload",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_FILE_TYPE"


def test_upload_rejects_invalid_pdf_bytes(client):
    r = client.post(
        "/api/files/upload",
        files={"file": ("bad.pdf", b"%PDF-1.4 not really", "application/pdf")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_PDF"


def test_upload_and_job_flow(client, minimal_pdf_path):
    with open(minimal_pdf_path, "rb") as f:
        raw = f.read()
    up = client.post(
        "/api/files/upload",
        files={"file": ("plan.pdf", io.BytesIO(raw), "application/pdf")},
    )
    assert up.status_code == 200
    body = up.json()
    assert "fileId" in body
    assert body["pageCount"] >= 1

    cr = client.post(
        "/api/jobs",
        json={
            "fileId": body["fileId"],
            "pageSelectionMode": "all",
            "pageNumbers": [1],
            "outputFormats": ["png", "json"],
        },
    )
    assert cr.status_code == 200
    job_id = cr.json()["jobId"]

    st = client.get(f"/api/jobs/{job_id}")
    assert st.status_code == 200
    assert st.json()["status"] in ("queued", "processing", "completed", "failed")

    res = client.get(f"/api/jobs/{job_id}/result")
    assert res.status_code == 200
    result = res.json()
    assert result["jobId"] == job_id
    if result["status"] == "completed":
        assert result.get("summary") is not None
        seg = client.get(f"/api/jobs/{job_id}/segments")
        assert seg.status_code == 200
        assert "segments" in seg.json()


def test_create_job_unknown_file(client):
    r = client.post(
        "/api/jobs",
        json={"fileId": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_get_job_unknown(client):
    r = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_files_path_traversal_blocked(client):
    r = client.get("/files/../app/main.py")
    assert r.status_code in (403, 404)


def test_files_rejects_inputs_and_non_outputs(client):
    r = client.get("/files/inputs/abc/original.pdf")
    assert r.status_code == 403


def test_admin_jobs_list(client):
    r = client.get("/api/admin/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()


@pytest.fixture
def secure_client(monkeypatch):
    monkeypatch.setenv("HVAC_SECURE_DEPLOYMENT", "true")
    monkeypatch.setenv("HVAC_VIEWER_TOKEN_SECRET", "unit-test-secret")
    from importlib import reload

    import app.api.routes as routes_mod
    import app.core.config as config_mod
    import app.core.viewer_token as viewer_mod
    import app.main as main_mod

    reload(config_mod)
    reload(viewer_mod)
    reload(routes_mod)
    reload(main_mod)

    with TestClient(main_mod.app) as client:
        yield client

    monkeypatch.delenv("HVAC_SECURE_DEPLOYMENT", raising=False)
    monkeypatch.delenv("HVAC_VIEWER_TOKEN_SECRET", raising=False)
    reload(config_mod)
    reload(viewer_mod)
    reload(routes_mod)
    reload(main_mod)


def test_secure_deployment_blocks_public_files_and_admin(secure_client):
    client = secure_client
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/api/admin/jobs").status_code == 404
    assert client.get("/files/jobs/x/outputs/a.png").status_code == 404
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/assets/index.js.map").status_code == 404


def test_secure_job_endpoints_require_viewer_token(secure_client, minimal_pdf_path):
    client = secure_client
    with open(minimal_pdf_path, "rb") as f:
        raw = f.read()
    up = client.post(
        "/api/files/upload",
        files={"file": ("plan.pdf", io.BytesIO(raw), "application/pdf")},
    )
    assert up.status_code == 200
    file_id = up.json()["fileId"]

    cr = client.post("/api/jobs", json={"fileId": file_id, "pageSelectionMode": "all"})
    assert cr.status_code == 200
    payload = cr.json()
    job_id = payload["jobId"]
    token = payload["viewerToken"]
    assert token

    assert client.get(f"/api/jobs/{job_id}").status_code == 401
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 401
    assert client.get(f"/api/jobs/{job_id}/segments").status_code == 401
    assert client.get(f"/api/jobs/{job_id}/preview").status_code == 401

    headers = {"X-Job-Viewer-Token": token}
    assert client.get(f"/api/jobs/{job_id}", headers=headers).status_code == 200
    assert client.get(f"/api/jobs/{job_id}/result", headers=headers).status_code == 200

"""
test_image_gallery_api.py
===========================
Regression tests for the bulk image gallery endpoint
(GET /documents/{job_id}/images, backend/routes.py::get_document_images).

Covers:
  * Strict image_XXX.png <-> image_XXX.json pairing (orphaned/raw/temp
    assets never appear in the response).
  * All required fields are present on every returned image.
  * The endpoint is NOT limited by chat retrieval's top_k caps -- every
    valid pair is returned regardless of count.
  * 404 for an unknown job.
  * End-to-end against the real btl_216_page_run 05_images fixture:
    total PNGs == total JSONs == API images returned, and portraits +
    charts/diagrams are present among them.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
import backend.routes as routes


def _write_pair(images_dir: Path, seq: str, **fields):
    png_path = images_dir / f"{seq}.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngbytes")
    data = {
        "image_id": f"id_{seq}", "image_path": f"05_images/{seq}.png",
        "image_url": f"/outputs/test_job/05_images/{seq}.png", "page": 1,
        "image_type": "Photo", "semantic_description": f"Description for {seq}",
        "entity_name": None, "designation": None, "caption": f"Caption {seq}",
        "keywords": ["photo"], "retrievable": True,
    }
    data.update(fields)
    (images_dir / f"{seq}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def gallery_job_dir(tmp_path, monkeypatch):
    job_id = "test_gallery_job"
    job_dir = tmp_path / "data" / "output" / job_id
    images_dir = job_dir / "05_images"
    images_dir.mkdir(parents=True)

    # Valid strict pairs
    _write_pair(images_dir, "image_001", image_type="Portrait Photo", entity_name="Mr. Test Person", designation="Director")
    _write_pair(images_dir, "image_002", image_type="Logo")
    _write_pair(images_dir, "image_003", image_type="Chart/Graph", retrievable=False)

    # Orphaned JSON with no matching PNG -- must NOT appear
    (images_dir / "image_004.json").write_text(json.dumps({"image_id": "orphan_json"}), encoding="utf-8")

    # Orphaned PNG with no matching JSON -- must NOT appear
    (images_dir / "image_005.png").write_bytes(b"\x89PNG orphan")

    # 0-byte PNG with a JSON -- must NOT appear (not a valid physical asset)
    (images_dir / "image_006.png").write_bytes(b"")
    (images_dir / "image_006.json").write_text(json.dumps({"image_id": "zero_byte"}), encoding="utf-8")

    # Non-canonical / raw staging artefact -- must NOT appear
    (images_dir / "_raw_staging_001.png").write_bytes(b"\x89PNG raw")
    (images_dir / "_raw_staging_001.json").write_text(json.dumps({"image_id": "raw"}), encoding="utf-8")

    monkeypatch.setattr(routes, "get_job", lambda jid: {"job_id": jid, "status": "completed"} if jid == job_id else None)
    monkeypatch.setattr(routes, "get_job_dir", lambda jid: job_dir)

    return job_id, job_dir


def test_gallery_returns_only_strict_pairs(gallery_job_dir):
    job_id, _ = gallery_job_dir
    client = TestClient(app)
    resp = client.get(f"/api/documents/{job_id}/images")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_images"] == 3
    seq_names = {img["seq_name"] for img in data["images"]}
    assert seq_names == {"image_001", "image_002", "image_003"}
    for orphan in ("image_004", "image_005", "image_006", "_raw_staging_001"):
        assert orphan not in seq_names


def test_gallery_response_has_all_required_fields(gallery_job_dir):
    job_id, _ = gallery_job_dir
    client = TestClient(app)
    data = client.get(f"/api/documents/{job_id}/images").json()

    required_fields = {
        "image_id", "image_path", "image_url", "page", "image_type",
        "semantic_description", "entity_name", "designation", "caption",
        "keywords", "retrievable",
    }
    for img in data["images"]:
        assert required_fields.issubset(img.keys()), img.keys()

    portrait = next(img for img in data["images"] if img["seq_name"] == "image_001")
    assert portrait["entity_name"] == "Mr. Test Person"
    assert portrait["designation"] == "Director"
    assert portrait["retrievable"] is True

    low_conf = next(img for img in data["images"] if img["seq_name"] == "image_003")
    assert low_conf["retrievable"] is False


def test_gallery_not_capped_by_chat_top_k(tmp_path, monkeypatch):
    """
    Chat retrieval caps results (e.g. top_k_final=8 for visual queries). The
    gallery endpoint must return every valid pair regardless -- here, more
    than any chat top_k cap.
    """
    job_id = "test_gallery_uncapped"
    job_dir = tmp_path / "data" / "output" / job_id
    images_dir = job_dir / "05_images"
    images_dir.mkdir(parents=True)

    N = 40
    for i in range(1, N + 1):
        _write_pair(images_dir, f"image_{i:03d}")

    monkeypatch.setattr(routes, "get_job", lambda jid: {"job_id": jid, "status": "completed"} if jid == job_id else None)
    monkeypatch.setattr(routes, "get_job_dir", lambda jid: job_dir)

    client = TestClient(app)
    data = client.get(f"/api/documents/{job_id}/images").json()
    assert data["total_images"] == N
    assert len(data["images"]) == N


def test_gallery_404_for_unknown_job(monkeypatch):
    monkeypatch.setattr(routes, "get_job", lambda jid: None)
    client = TestClient(app)
    resp = client.get("/api/documents/does-not-exist/images")
    assert resp.status_code == 404


def test_gallery_empty_when_no_images_dir(tmp_path, monkeypatch):
    job_id = "test_gallery_no_images"
    job_dir = tmp_path / "data" / "output" / job_id
    job_dir.mkdir(parents=True)

    monkeypatch.setattr(routes, "get_job", lambda jid: {"job_id": jid, "status": "completed"} if jid == job_id else None)
    monkeypatch.setattr(routes, "get_job_dir", lambda jid: job_dir)

    client = TestClient(app)
    data = client.get(f"/api/documents/{job_id}/images").json()
    assert data["total_images"] == 0
    assert data["images"] == []


# ---------------------------------------------------------------------------
# End-to-end against the real btl_216_page_run fixture
# ---------------------------------------------------------------------------

REAL_JOB_ID = "btl_216_page_run"
REAL_JOB_DIR = Path(__file__).resolve().parent.parent / "data" / "output" / REAL_JOB_ID
REAL_IMAGES_DIR = REAL_JOB_DIR / "05_images"


@pytest.mark.skipif(not REAL_IMAGES_DIR.exists(), reason="real btl_216_page_run fixture not present")
def test_gallery_matches_physical_asset_counts_on_real_document():
    total_pngs = len(list(REAL_IMAGES_DIR.glob("image_*.png")))
    total_jsons = len(list(REAL_IMAGES_DIR.glob("image_*.json")))
    assert total_pngs == total_jsons, "05_images must maintain strict 1:1 PNG<->JSON pairing"

    import backend.routes as routes_mod
    orig_get_job, orig_get_job_dir = routes_mod.get_job, routes_mod.get_job_dir
    routes_mod.get_job = lambda jid: {"job_id": jid, "status": "completed"} if jid == REAL_JOB_ID else None
    routes_mod.get_job_dir = lambda jid: REAL_JOB_DIR
    try:
        client = TestClient(app)
        data = client.get(f"/api/documents/{REAL_JOB_ID}/images").json()
    finally:
        routes_mod.get_job, routes_mod.get_job_dir = orig_get_job, orig_get_job_dir

    assert data["total_images"] == total_pngs == total_jsons
    image_types = {img["image_type"] for img in data["images"]}
    assert "Portrait Photo" in image_types, "portraits must be present in the gallery"
    assert any(t in image_types for t in ("Chart/Graph", "Chart", "Graph", "Diagram")), \
        "charts/diagrams must be present in the gallery"
    assert all("image_id" in img and "semantic_description" in img for img in data["images"])

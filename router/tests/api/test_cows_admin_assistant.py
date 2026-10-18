"""HTTP API without the models: health, access control, cows, the vet-document library, error mapping and the rate limit."""
import base64


def test_health_and_status(client):
    assert client.get("/health").json() == {"status": "ok"}
    s = client.get("/api/status").json()
    assert s["infer_backend"] == "local" and s["cows"] == 0 and s["kb_sources"] == {}


def test_every_response_has_the_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_the_web_app_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "GoMitra" in r.text
    assert client.get("/static/samples/index.json").status_code == 200


# ---- admin and device keys
def test_admin_routes_need_the_admin_key(client, admin):
    for method, path in [("post", "/api/demo/seed"), ("post", "/api/demo/history"), ("post", "/api/demo/reset"),
                         ("delete", "/api/cows/x"), ("post", "/api/admin/kb"), ("delete", "/api/admin/kb/x")]:
        assert getattr(client, method)(path).status_code == 403, path
        assert getattr(client, method)(path, headers={"x-admin-key": "wrong"}).status_code == 403, path
    assert client.post("/api/demo/seed", headers=admin).status_code == 200


def test_the_device_route_needs_the_device_key(client, device):
    body = {"file": base64.b64encode(b"hello world").decode()}
    assert client.post("/api/ingest", json=body).status_code == 403
    assert client.post("/api/ingest", json=body, headers={"x-device-key": "no"}).status_code == 403
    r = client.post("/api/ingest", json=body, headers=device)
    assert r.status_code == 415 and "JPEG" in r.json()["detail"]


# ---- cows
def test_seed_adds_the_six_demo_cows_once(client, admin):
    assert client.post("/api/demo/seed", headers=admin).json() == {"added": 6}
    assert client.post("/api/demo/seed", headers=admin).json() == {"added": 0}
    cows = client.get("/api/cows").json()
    assert len(cows) == 6 and all("embeddings" not in c and "history" not in c for c in cows)       # never sent to the app


def test_unknown_cow_is_404_everywhere(client):
    for path in ("/api/cows/nobody", "/api/cows/nobody/trends", "/api/cows/nobody/report"):
        r = client.get(path)
        assert r.status_code == 404 and r.json() == {"detail": "cow not found"}, path
    assert client.post("/api/cows/nobody/resolve").status_code == 404


def test_register_without_photos_needs_a_tag_and_warns_about_faces(client):
    assert client.post("/api/cows", json={"tag": "  ", "photos": {}}).status_code == 400
    r = client.post("/api/cows", json={"name": "Test Cow", "tag": "0999", "breed": "Gir", "age": "4", "photos": {}}).json()
    assert r["cow"]["id"] == "test-cow-0999" and r["faces_found"] == 0 and "ear tag" in r["warning"]
    assert client.get("/api/cows/test-cow-0999").json()["name"] == "Test Cow"


def test_cows_needing_attention_come_first_and_resolve_clears_the_alert(client, admin):
    from gomitra.context import store
    client.post("/api/demo/seed", headers=admin)
    store.update("cows", "tulasi", {"alert": True, "kind": "down", "msg": {"en": {}}, "signals": {"walking": "check"}, "history": ["lumpy"]})
    assert client.get("/api/cows").json()[0]["id"] == "tulasi"
    assert client.post("/api/cows/tulasi/resolve").json() == {"ok": True}
    c = client.get("/api/cows/tulasi").json()
    assert c["alert"] is False and c["kind"] is None and c["signals"] == {}
    assert client.delete("/api/cows/tulasi", headers=admin).json() == {"ok": True}
    assert client.get("/api/cows/tulasi").status_code == 404


# ---- vet documents and the assistant
def test_the_vet_document_library(client, admin):
    r = client.post("/api/admin/kb", headers=admin, json={"source": "notes", "text": "Lumpy skin disease spreads by biting flies."})
    assert r.json() == {"source": "notes", "chunks": 1}
    assert client.get("/api/kb").json() == {"notes": 1}
    assert client.delete("/api/admin/kb/notes", headers=admin).json() == {"removed": 1}
    assert client.get("/api/kb").json() == {}


def test_a_pdf_can_be_uploaded(client, admin):
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO(); c = canvas.Canvas(buf); c.drawString(60, 780, "Bloat is a swollen left side after wet green fodder."); c.save()
    r = client.post("/api/admin/kb", headers=admin, json={"source": "pdf", "pdf": base64.b64encode(buf.getvalue()).decode()})
    assert r.status_code == 200 and r.json()["chunks"] == 1


def test_ask_rejects_an_unknown_language_and_reports_an_unavailable_assistant(client, admin):
    assert client.post("/api/ask", json={"question": "x", "lang": "fr"}).status_code == 400
    client.post("/api/admin/kb", headers=admin, json={"source": "notes", "text": "Lumpy skin disease spreads by biting flies."})
    r = client.post("/api/ask", json={"question": "lumpy skin disease biting flies", "lang": "en"})
    assert r.status_code == 502 and "assistant unavailable" in r.json()["detail"]          # Gemini is not reachable in tests


def test_ask_with_nothing_relevant_says_it_does_not_know(client):
    r = client.post("/api/ask", json={"question": "zzzz qqqq", "lang": "te"}).json()
    assert r["grounded"] is False and r["sources"] == [] and r["trace"] is not None


# ---- rate limit
def test_the_rate_limit_blocks_a_visitor_but_not_another_or_the_admin(client, admin):
    ip = {"x-forwarded-for": "1.1.1.1"}
    codes = [client.post("/api/posture", json={"images": []}, headers=ip).status_code for _ in range(22)]
    assert codes[:20] == [400] * 20 and codes[20:] == [429, 429]
    assert client.post("/api/posture", json={"images": []}, headers=ip).headers["retry-after"] == "60"
    assert client.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "2.2.2.2"}).status_code == 400
    assert client.post("/api/posture", json={"images": []}, headers={**ip, **admin}).status_code == 400
    assert client.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "9.9.9.9, 2.2.2.2"}).status_code == 400


def test_the_warmup_is_limited_more_tightly(client):
    ip = {"x-forwarded-for": "3.3.3.3"}
    assert [client.post("/api/warmup", headers=ip).status_code for _ in range(8)] == [200] * 6 + [429] * 2

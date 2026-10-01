"""A server failure must reach the browser as a readable 500. Found in the browser pass: the /demo page reported
"Network error" for every one of 488 uploads. An unhandled exception was answered outside the CORS middleware, so
the response had no CORS headers and the browser threw it away."""

from fastapi.testclient import TestClient

from app.main import create_app

ORIGIN = {"Origin": "http://localhost:3000", "Authorization": "Bearer dev-recruiter-token"}


def test_an_unhandled_error_is_a_readable_500_with_cors_headers():
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("database exploded")

    response = TestClient(app, raise_server_exceptions=False).get("/boom", headers=ORIGIN)
    assert response.status_code == 500
    assert response.json() == {"detail": "server_error"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "exploded" not in response.text  # the cause is logged, never sent to the browser


def test_a_failing_upload_route_is_readable_by_the_browser(monkeypatch, session):
    from app.api import routes
    from app.bootstrap import provision

    provision(session)
    session.commit()

    def broken(*args, **kwargs):
        raise OSError("storage volume is read-only")

    monkeypatch.setattr(routes, "ingest_bytes", broken)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post("/documents", headers=ORIGIN, files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

"""The HTTP shell: the four ``api/*.py`` Vercel functions, invoked in-process.

``BaseHTTPRequestHandler`` needs no socket if you hand it an ``rfile`` and a
``wfile``, so these tests exercise the real handler classes — status lines,
headers, body bytes — without a server, a port or a Vercel emulator.
"""

from __future__ import annotations

import email.message
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
API_DIR = APP_ROOT / "api"


def _load(module_name: str, filename: str):
    """Load an ``api/*.py`` file the way Vercel's Python runtime does."""
    spec = importlib.util.spec_from_file_location(module_name, API_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


COMPARE = _load("structura_api_compare", "compare.py")
EXPORT = _load("structura_api_export", "export.py")
REFERENCE_DEALS = _load("structura_api_reference_deals", "reference_deals.py")
CURRENT_LAW = _load("structura_api_current_law", "current_law.py")


class Response:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: dict, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def call(module, method: str, body: bytes = b"", content_length=None) -> Response:
    cls = module.handler
    request_handler = cls.__new__(cls)
    request_handler.rfile = io.BytesIO(body)
    request_handler.wfile = io.BytesIO()
    headers = email.message.Message()
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = (
        str(len(body)) if content_length is None else str(content_length)
    )
    request_handler.headers = headers
    request_handler.request_version = "HTTP/1.1"
    request_handler.requestline = f"{method} / HTTP/1.1"
    request_handler.client_address = ("127.0.0.1", 0)
    request_handler.server = None
    request_handler.command = method
    request_handler.path = "/"
    getattr(request_handler, f"do_{method}")()

    raw = request_handler.wfile.getvalue()
    head, _, payload = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1])
    parsed = {}
    for line in lines[1:]:
        if ": " in line:
            name, value = line.split(": ", 1)
            parsed[name] = value
    return Response(status, parsed, payload)


def post(module, payload) -> Response:
    return call(module, "POST", json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# /api/compare
# ---------------------------------------------------------------------------


def test_compare_returns_the_contract_payload():
    response = post(COMPARE, {"deal_key": "storage_bess_contracted"})
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert int(response.headers["Content-Length"]) == len(response.body)
    payload = response.json()
    assert payload["ranked"][0]["key"] == "partnership_flip"
    assert payload["ranked"][0]["sponsor_after_tax_irr"] == pytest.approx(
        0.1485, abs=5e-5
    )
    assert payload["compute_ms"] > 0


def test_compare_accepts_an_empty_body():
    response = call(COMPARE, "POST")
    assert response.status == 200
    assert any("no 'deal_key'" in w for w in response.json()["warnings"])


def test_compare_applies_overrides_end_to_end():
    base = post(COMPARE, {"deal_key": "storage_bess_contracted"}).json()
    bumped = post(
        COMPARE,
        {
            "deal_key": "storage_bess_contracted",
            "overrides": {"interest_rate": 0.09, "target_dscr": 1.45},
        },
    ).json()
    assert bumped["debt"]["quantum"] != base["debt"]["quantum"]
    assert bumped["ranked"][0]["sponsor_after_tax_irr"] != base["ranked"][0][
        "sponsor_after_tax_irr"
    ]


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"deal_key": "does_not_exist"}, "deal_key"),
        ({"overrides": {"capex": "a lot"}}, "capex"),
        ({"overrides": {"interest_rate": 4}}, "interest_rate"),
        ({"overrides": {"project_life_years": 400}}, "project_life_years"),
        ({"overrides": {"technology": "COLD_FUSION"}}, "technology"),
    ],
)
def test_compare_rejects_bad_input_with_400_and_a_field(payload, field):
    response = post(COMPARE, payload)
    assert response.status == 400
    body = response.json()
    assert body["field"] == field
    assert "Traceback" not in body["error"]


def test_compare_rejects_malformed_json():
    response = call(COMPARE, "POST", b'{"deal_key": ')
    assert response.status == 400
    assert "error" in response.json()


def test_compare_rejects_an_oversized_body():
    response = call(COMPARE, "POST", b"{}", content_length=10_000_000)
    assert response.status == 413


def test_compare_rejects_wrong_method():
    response = call(COMPARE, "GET")
    assert response.status == 405
    assert response.headers["Allow"] == "POST, OPTIONS"


def test_compare_answers_a_cors_preflight():
    response = call(COMPARE, "OPTIONS")
    assert response.status == 204
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


def test_no_stack_trace_ever_reaches_the_client(monkeypatch):
    def boom(_body):
        raise RuntimeError("secret internal detail /var/task/engine/debt.py:123")

    monkeypatch.setattr(COMPARE, "run_compare", boom)
    response = post(COMPARE, {})
    assert response.status == 500
    body = response.json()
    assert set(body) == {"error"}
    assert "secret internal detail" not in body["error"]
    assert "Traceback" not in body["error"]
    assert "debt.py" not in body["error"]


# ---------------------------------------------------------------------------
# /api/export
# ---------------------------------------------------------------------------


def test_export_returns_a_real_workbook():
    response = post(EXPORT, {"deal_key": "storage_bess_contracted"})
    assert response.status == 200
    assert response.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["Content-Disposition"].startswith(
        'attachment; filename="structura-storage_bess_contracted-'
    )
    assert response.headers["Content-Disposition"].endswith('.xlsx"')
    assert response.body[:2] == b"PK"
    assert int(response.headers["Content-Length"]) == len(response.body)
    # Comfortably inside the 4.5 MB Vercel body cap.
    assert len(response.body) < 4 * 1024 * 1024
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        names = archive.namelist()
        assert "xl/workbook.xml" in names
        # SPEC §9 gate: iterative calculation must survive the round trip.
        assert 'iterate="1"' in archive.read("xl/workbook.xml").decode()


def test_export_over_the_cap_returns_413_json(monkeypatch):
    from lib_api import service

    monkeypatch.setattr(service, "MAX_EXPORT_BYTES", 1024)
    response = post(EXPORT, {"deal_key": "storage_bess_contracted"})
    assert response.status == 413
    body = response.json()
    assert "error" in body
    assert body["limit_bytes"] == 1024
    assert body["bytes"] > 1024


def test_export_validates_its_input_too():
    response = post(EXPORT, {"overrides": {"capex": -1}})
    assert response.status == 400
    assert response.json()["field"] == "capex"


def test_export_rejects_an_unknown_structure():
    response = post(EXPORT, {"structure": "yieldco"})
    assert response.status == 400
    assert response.json()["field"] == "structure"


def test_export_rejects_wrong_method():
    assert call(EXPORT, "GET").status == 405


# ---------------------------------------------------------------------------
# /api/reference-deals and /api/current-law
# ---------------------------------------------------------------------------


def test_reference_deals_endpoint():
    response = call(REFERENCE_DEALS, "GET")
    assert response.status == 200
    deals = response.json()["deals"]
    assert {d["key"] for d in deals} == {
        "storage_bess_contracted",
        "solar_safe_harboured",
        "data_center_powered_shell",
    }


def test_reference_deals_rejects_post():
    assert call(REFERENCE_DEALS, "POST", b"{}").status == 405


def test_current_law_endpoint():
    response = call(CURRENT_LAW, "GET")
    assert response.status == 200
    payload = response.json()
    assert payload["law_verified_on"] == "2026-08-06"
    assert payload["citations"]
    assert payload["unverified"]
    assert payload["litigation"]["toggle_values"] == [
        "vacated",
        "reinstated_on_appeal",
    ]


def test_current_law_rejects_post():
    assert call(CURRENT_LAW, "POST", b"{}").status == 405


# ---------------------------------------------------------------------------
# Deployment hygiene
# ---------------------------------------------------------------------------


def test_every_endpoint_file_exposes_a_vercel_handler():
    for module in (COMPARE, EXPORT, REFERENCE_DEALS, CURRENT_LAW):
        assert hasattr(module, "handler")
        assert module.handler.__name__ == "handler"


def test_vercel_json_declares_the_python_functions_and_the_hyphen_rewrites():
    config = json.loads((APP_ROOT / "vercel.json").read_text())
    assert "api/**/*.py" in config["functions"]
    rewrites = {r["source"]: r["destination"] for r in config["rewrites"]}
    assert rewrites["/api/reference-deals"] == "/api/reference_deals"
    assert rewrites["/api/current-law"] == "/api/current_law"


def test_requirements_pin_every_runtime_dependency():
    text = (APP_ROOT / "requirements.txt").read_text()
    for package in ("scipy==", "numpy==", "pyxirr==", "openpyxl=="):
        assert package in text
    # pytest is a dev dependency; shipping it wastes ~14 MB of bundle.
    assert "pytest" not in text

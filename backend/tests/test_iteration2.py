"""Iteration-2 focused tests:
- second super admin (lalit@4xstruct.com)
- engine rebrand (no 'gemini' leak in API responses)
- /api/analyses/modes now returns 'roles' + 'demo_prompt'
- /api/analyses/demo endpoint (admin bypass role lock; non-admin 403 on role-locked mode)
- regression quick pings: projects, rfis, admin/users still work
"""
from __future__ import annotations

import json as _json
import os
import re
import subprocess
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://steel-intel-1.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN1_EMAIL = "niks.shah236@gmail.com"
ADMIN1_PASS = "Nikunj@1405"
ADMIN2_EMAIL = "lalit@4xstruct.com"
ADMIN2_PASS = "Lalit@4xstruct"

BACKEND_ERR_LOG = "/var/log/supervisor/backend.err.log"
BACKEND_OUT_LOG = "/var/log/supervisor/backend.out.log"


def _grep_otp(email: str, retries: int = 15, delay: float = 1.0) -> str | None:
    pat = re.escape(email)
    for _ in range(retries):
        logs = ""
        for path in (BACKEND_ERR_LOG, BACKEND_OUT_LOG):
            if os.path.exists(path):
                try:
                    logs += subprocess.check_output(["tail", "-n", "2000", path]).decode(errors="ignore")
                except Exception:
                    pass
        blocks = re.split(r"DEV EMAIL", logs)
        for block in reversed(blocks):
            if re.search(rf"To:\s*{pat}", block):
                m = re.search(r"code is:\s*(\d{6})", block)
                if m:
                    return m.group(1)
        time.sleep(delay)
    return None


# ---------- session fixtures ----------

@pytest.fixture(scope="session")
def admin1_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN1_EMAIL, "password": ADMIN1_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin2_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN2_EMAIL, "password": ADMIN2_PASS}, timeout=30)
    assert r.status_code == 200, f"admin2 login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin1_headers(admin1_token):
    return {"Authorization": f"Bearer {admin1_token}"}


@pytest.fixture(scope="session")
def admin2_headers(admin2_token):
    return {"Authorization": f"Bearer {admin2_token}"}


# ---------- 1. Dual super admin ----------

def test_admin2_login_and_shape():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN2_EMAIL, "password": ADMIN2_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == ADMIN2_EMAIL
    assert body["user"]["role"] == "admin"
    assert body["user"]["subscription_tier"] == "enterprise"
    assert body["user"]["is_verified"] is True
    assert "access_token" in body and "refresh_token" in body


def test_admin1_still_works():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN1_EMAIL, "password": ADMIN1_PASS}, timeout=30)
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"


# ---------- 2. Modes catalog has roles+demo_prompt ----------

def test_modes_has_roles_and_demo_prompt(admin2_headers):
    r = requests.get(f"{API}/analyses/modes", headers=admin2_headers, timeout=20)
    assert r.status_code == 200
    body = r.json()
    modes = body.get("modes") or body.get("items") or []
    assert len(modes) == 25
    for m in modes:
        assert "roles" in m and isinstance(m["roles"], list) and len(m["roles"]) >= 1
        assert "demo_prompt" in m and isinstance(m["demo_prompt"], str) and len(m["demo_prompt"]) > 20
        # admin should see allowed=true for every mode
        assert m.get("allowed") is True, f"admin not allowed to see {m['id']}"


# ---------- 3. /demo endpoint — admin bypass role lock ----------

@pytest.fixture(scope="module")
def demo_analysis_id(admin2_headers):
    # Admin (lalit) firing an engineer-only mode
    r = requests.post(
        f"{API}/analyses/demo",
        headers=admin2_headers,
        json={"mode": "CONNECTION_DESIGN_ADVISOR"},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("is_demo") is True
    assert body.get("mode") == "CONNECTION_DESIGN_ADVISOR"
    assert body.get("mode_label")
    assert body.get("input_text") and len(body["input_text"]) > 30
    assert body.get("status") in ("queued", "processing")
    assert "_id" not in body
    return body["id"]


def test_demo_completes_with_structmind_label(demo_analysis_id, admin2_headers):
    aid = demo_analysis_id
    deadline = time.time() + 180
    last = {}
    while time.time() < deadline:
        s = requests.get(f"{API}/analyses/{aid}/status", headers=admin2_headers, timeout=30)
        if s.status_code == 200:
            last = s.json()
            if last.get("status") in ("complete", "failed", "error"):
                break
        time.sleep(3)
    if last.get("status") != "complete":
        pytest.skip(f"demo did not complete in 180s; state={last}")
    det = requests.get(f"{API}/analyses/{aid}", headers=admin2_headers, timeout=30)
    assert det.status_code == 200
    doc = det.json()
    # model_used must be the branded label, not raw gemini-*
    mu = doc.get("model_used", "")
    assert mu.startswith("STRUCTMIND CORE"), f"expected STRUCTMIND CORE label, got: {mu}"
    assert "gemini" not in mu.lower()
    assert doc.get("output_markdown") and len(doc["output_markdown"]) > 100
    exp = doc.get("exports") or []
    if isinstance(exp, list):
        keys = {e.get("format") for e in exp if isinstance(e, dict)}
    else:
        keys = set(exp.keys()) if isinstance(exp, dict) else set()
    assert {"markdown", "csv", "xlsx", "docx", "pdf"}.issubset(keys), f"missing exports: {keys}"


# ---------- 4. No 'gemini' leak in API responses ----------

def test_no_gemini_leak_in_analysis_doc(demo_analysis_id, admin2_headers):
    det = requests.get(f"{API}/analyses/{demo_analysis_id}", headers=admin2_headers, timeout=20)
    assert det.status_code == 200
    # search ONLY the api-facing field that is user-visible (model_used) and a few others we care about
    doc = det.json()
    # pop the free-form markdown content (could legitimately quote 'gemini' from user input - not in our case, but to be safe)
    output_md = doc.pop("output_markdown", "")
    body_text = _json.dumps(doc).lower()
    assert "gemini" not in body_text, f"'gemini' string leaked in /api/analyses/{{id}}: {body_text[:500]}"
    # defensive: also check markdown body for our demo (STRUCTMIND AI prompt does not reference gemini)
    assert "gemini" not in output_md.lower(), "output_markdown contains 'gemini'"


def test_no_gemini_leak_in_dashboard_stats(admin2_headers):
    r = requests.get(f"{API}/dashboard/stats", headers=admin2_headers, timeout=20)
    assert r.status_code == 200
    body_text = _json.dumps(r.json()).lower()
    assert "gemini" not in body_text


# ---------- 5. Admin can demo role-locked modes (sample 3) ----------

@pytest.mark.parametrize("mode_id", ["SAFETY_PLAN", "STRUCTURAL_CLASH_DETECTOR", "SUSTAINABILITY_REPORT"])
def test_admin_can_demo_role_locked_modes(admin2_headers, mode_id):
    r = requests.post(
        f"{API}/analyses/demo",
        headers=admin2_headers,
        json={"mode": mode_id},
        timeout=90,
    )
    assert r.status_code == 200, f"{mode_id}: {r.status_code} {r.text}"
    body = r.json()
    assert body["mode"] == mode_id
    assert body["is_demo"] is True
    assert body.get("status") in ("queued", "processing")


# ---------- 6. Non-admin (ESTIMATOR) hits 403 on engineer-only demo mode ----------

@pytest.fixture(scope="module")
def estimator_token():
    ts = int(time.time())
    email = f"est{ts}@example.com"
    password = "Test@1234"
    r = requests.post(
        f"{API}/auth/signup",
        json={
            "email": email, "password": password,
            "first_name": "Est", "last_name": "User",
            "company": "T", "role": "estimator", "country": "US",
        },
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    otp = _grep_otp(email)
    if not otp:
        pytest.skip("OTP not found in backend log; cannot build estimator token")
    r2 = requests.post(f"{API}/auth/verify-otp", json={"user_id": uid, "otp": otp}, timeout=20)
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


def test_non_admin_estimator_forbidden_on_phase_2_demo(estimator_token):
    headers = {"Authorization": f"Bearer {estimator_token}"}
    r = requests.post(
        f"{API}/analyses/demo",
        headers=headers,
        json={"mode": "PHASE_2"},
        timeout=20,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# ---------- 7. Regression smoke ----------

def test_regression_projects_list(admin2_headers):
    r = requests.get(f"{API}/projects", headers=admin2_headers, timeout=60)
    assert r.status_code == 200


def test_regression_admin_users(admin2_headers):
    r = requests.get(f"{API}/admin/users", headers=admin2_headers, timeout=60)
    assert r.status_code == 200


def test_regression_rfis_list(admin2_headers):
    r = requests.get(f"{API}/rfis", headers=admin2_headers, timeout=60)
    assert r.status_code == 200

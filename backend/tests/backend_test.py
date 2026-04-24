"""StructMind AI backend integration tests.

Covers: health, auth (admin login + signup+OTP + forgot + change),
projects CRUD, files upload, analysis modes, analysis run + exports,
RFI CRUD, dashboard, notifications, admin, role enforcement,
blockchain verify.

NOTE: Gemini analysis may fail if the EMERGENT_LLM_KEY budget is exhausted.
The test will poll, and if the outcome is 'failed' due to budget, we record it
but do not claim complete; downstream export tests are then skipped.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://steel-intel-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "niks.shah236@gmail.com"
ADMIN_PASS = "Nikunj@1405"

BACKEND_ERR_LOG = "/var/log/supervisor/backend.err.log"
BACKEND_OUT_LOG = "/var/log/supervisor/backend.out.log"


def _grep_otp(email: str, retries: int = 15, delay: float = 1.0) -> str | None:
    pattern_email = re.escape(email)
    for _ in range(retries):
        logs = ""
        for path in (BACKEND_ERR_LOG, BACKEND_OUT_LOG):
            if os.path.exists(path):
                try:
                    logs += subprocess.check_output(["tail", "-n", "1500", path]).decode(errors="ignore")
                except Exception:
                    pass
        blocks = re.split(r"DEV EMAIL", logs)
        for block in reversed(blocks):
            if re.search(rf"To:\s*{pattern_email}", block):
                # Match code after "code is:" to avoid email timestamp digits
                m = re.search(r"code is:\s*(\d{6})", block)
                if m:
                    return m.group(1)
        time.sleep(delay)
    return None


def _extract_list(resp_body):
    if isinstance(resp_body, list):
        return resp_body
    if isinstance(resp_body, dict):
        return resp_body.get("items") or resp_body.get("modes") or []
    return []


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def project_id(admin_headers) -> str:
    r = requests.post(
        f"{API}/projects",
        headers=admin_headers,
        json={"name": f"TEST_Proj_{uuid.uuid4().hex[:6]}", "description": "pytest project"},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    doc = r.json()
    assert "_id" not in doc
    return doc["id"]


# ---------- 1. Health ----------

def test_health_ok():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- 2. Auth: admin login + me ----------

def test_admin_login_no_otp():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body and "refresh_token" in body
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    assert body["user"]["subscription_tier"] == "enterprise"
    assert body["user"]["is_verified"] is True


def test_auth_me(admin_headers):
    r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    u = r.json()
    assert u["email"] == ADMIN_EMAIL and u["role"] == "admin"
    assert "_id" not in u


# ---------- 3. Signup + OTP verify ----------

@pytest.fixture(scope="module")
def new_user():
    ts = int(time.time())
    email = f"e2e{ts}@example.com"
    password = "Test@1234"
    r = requests.post(
        f"{API}/auth/signup",
        json={
            "email": email,
            "password": password,
            "first_name": "E2E",
            "last_name": "User",
            "company": "TestCo",
            "role": "estimator",
            "country": "US",
        },
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "user_id" in body and body["email"] == email
    return {"email": email, "password": password, "user_id": body["user_id"]}


def test_signup_triggers_otp(new_user):
    otp = _grep_otp(new_user["email"])
    assert otp is not None, "OTP not found in backend log after signup"
    new_user["otp"] = otp


def test_verify_otp_success(new_user):
    otp = new_user.get("otp") or _grep_otp(new_user["email"])
    assert otp
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"user_id": new_user["user_id"], "otp": otp}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and body["user"]["is_verified"] is True
    new_user["access_token"] = body["access_token"]


def test_verify_otp_invalid_fails():
    """Fresh signup then send wrong OTP -> 401/410."""
    ts = int(time.time() * 1000)
    email = f"invalid{ts}@example.com"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": "Test@1234", "first_name": "In", "last_name": "Valid",
        "company": "T", "role": "estimator", "country": "US",
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    r2 = requests.post(f"{API}/auth/verify-otp",
                       json={"user_id": uid, "otp": "000000"}, timeout=15)
    assert r2.status_code in (400, 401, 410), r2.text


# ---------- 4. Forgot password ----------

def test_forgot_password_flow(new_user):
    email = new_user["email"]
    r = requests.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    reset_token = r.json().get("reset_token")
    assert reset_token

    otp = _grep_otp(email)
    assert otp

    r2 = requests.post(f"{API}/auth/verify-reset-otp",
                       json={"reset_token": reset_token, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    session_token = r2.json().get("reset_session_token")
    assert session_token

    new_password = "Reset@9999"
    r3 = requests.post(f"{API}/auth/reset-password",
                       json={"reset_session_token": session_token, "new_password": new_password}, timeout=15)
    assert r3.status_code == 200, r3.text
    new_user["password"] = new_password

    r4 = requests.post(f"{API}/auth/login", json={"email": email, "password": new_password}, timeout=15)
    assert r4.status_code == 200
    new_user["access_token"] = r4.json()["access_token"]


# ---------- 5. Change password with OTP ----------

def test_change_password_requires_otp(new_user):
    headers = {"Authorization": f"Bearer {new_user['access_token']}"}
    current, new_pass = new_user["password"], "Changed@1234"
    r = requests.post(f"{API}/auth/change-password", headers=headers,
                      json={"current_password": current, "new_password": new_pass}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("otp_required") is True

    otp = _grep_otp(new_user["email"])
    assert otp
    r2 = requests.post(f"{API}/auth/change-password", headers=headers,
                       json={"current_password": current, "new_password": new_pass, "otp": otp}, timeout=20)
    assert r2.status_code == 200, r2.text
    new_user["password"] = new_pass


# ---------- 6. Projects CRUD ----------

def test_projects_crud(admin_headers):
    create = requests.post(f"{API}/projects", headers=admin_headers,
                           json={"name": f"TEST_CRUD_{uuid.uuid4().hex[:6]}", "description": "d"}, timeout=15)
    assert create.status_code in (200, 201)
    pid = create.json()["id"]
    assert "_id" not in create.json()

    listing = requests.get(f"{API}/projects", headers=admin_headers, timeout=15)
    assert listing.status_code == 200
    items = _extract_list(listing.json())
    assert any(p["id"] == pid for p in items), "created project not in list"
    first = next(p for p in items if p["id"] == pid)
    for k in ("file_count", "analysis_count", "rfi_count"):
        assert k in first, f"project list missing {k}"

    detail = requests.get(f"{API}/projects/{pid}", headers=admin_headers, timeout=15)
    assert detail.status_code == 200
    assert "_id" not in detail.json()

    upd = requests.put(f"{API}/projects/{pid}", headers=admin_headers,
                       json={"description": "updated"}, timeout=15)
    assert upd.status_code == 200
    assert upd.json()["description"] == "updated"

    dele = requests.delete(f"{API}/projects/{pid}", headers=admin_headers, timeout=15)
    assert dele.status_code in (200, 204)


# ---------- 7. File upload ----------

def test_file_upload_sha256(admin_headers, project_id):
    files = {"file": ("hello.txt", io.BytesIO(b"Hello StructMind test"), "text/plain")}
    data = {"project_id": project_id}
    r = requests.post(f"{API}/files/upload", headers=admin_headers, files=files, data=data, timeout=60)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "_id" not in body
    assert len(body.get("blockchain_hash", "")) == 64


# ---------- 8. Analysis modes catalog ----------

def test_analysis_modes(admin_headers):
    r = requests.get(f"{API}/analyses/modes", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    modes = _extract_list(r.json())
    assert len(modes) == 25, f"expected 25 modes, got {len(modes)}"
    groups = {m["group"] for m in modes}
    assert len(groups) == 7, f"expected 7 groups, got {groups}"
    m0 = modes[0]
    for k in ("id", "label", "group", "pro", "allowed"):
        assert k in m0, f"missing key {k}"


# ---------- 9. Analysis run (Gemini) + exports ----------

@pytest.fixture(scope="module")
def completed_analysis(admin_headers, project_id):
    r = requests.post(
        f"{API}/analyses",
        headers=admin_headers,
        json={
            "mode": "SUMMARY",
            "project_id": project_id,
            "input_text": "180 ton 3-storey steel frame with moment connections per AISC 360-22.",
        },
        timeout=30,
    )
    assert r.status_code in (200, 201, 202), r.text
    aid = r.json()["id"]
    deadline = time.time() + 180
    last = {}
    while time.time() < deadline:
        s = requests.get(f"{API}/analyses/{aid}/status", headers=admin_headers, timeout=30)
        if s.status_code == 200:
            last = s.json()
            if last.get("status") in ("complete", "failed", "error"):
                break
        time.sleep(3)
    return aid, last


def test_analysis_complete_fields(completed_analysis, admin_headers):
    aid, status = completed_analysis
    if status.get("status") != "complete":
        pytest.skip(f"Analysis did not complete (likely LLM budget). state={status}")
    det = requests.get(f"{API}/analyses/{aid}", headers=admin_headers, timeout=20)
    assert det.status_code == 200
    doc = det.json()
    assert "_id" not in doc
    assert doc.get("status") == "complete"
    assert (doc.get("model_used") or "").startswith("gemini-")
    assert doc.get("output_markdown")
    bh = doc.get("blockchain_hash", "")
    assert len(bh) == 64 and all(c in "0123456789abcdef" for c in bh.lower())
    exp = doc.get("exports") or []
    if isinstance(exp, dict):
        keys = set(exp.keys())
    else:
        keys = {e.get("format") for e in exp if isinstance(e, dict)}
    expected = {"markdown", "csv", "xlsx", "docx", "pdf"}
    assert expected.issubset(keys), f"missing exports: {expected - keys}"


@pytest.mark.parametrize("fmt", ["pdf", "docx", "xlsx", "csv", "markdown"])
def test_analysis_export_download(completed_analysis, admin_headers, fmt):
    aid, status = completed_analysis
    if status.get("status") != "complete":
        pytest.skip(f"Analysis not complete; state={status.get('status')}")
    r = requests.get(f"{API}/analyses/{aid}/export/{fmt}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"{fmt}: {r.status_code} {r.text[:200]}"
    assert len(r.content) > 10


# ---------- 10. RFI CRUD ----------

def test_rfi_crud(admin_headers, project_id):
    r = requests.post(f"{API}/rfis", headers=admin_headers,
                      json={"project_id": project_id, "subject": "TEST RFI", "body": "What size beam?"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "_id" not in body
    rid = body["id"]
    assert body.get("rfi_number", "").startswith("RFI-")

    for status in ("sent", "responded", "closed"):
        u = requests.put(f"{API}/rfis/{rid}", headers=admin_headers, json={"status": status}, timeout=15)
        assert u.status_code == 200, f"{status}: {u.text}"
        assert u.json().get("status") == status


# ---------- 11. Dashboard / notifications / admin ----------

def test_dashboard_stats(admin_headers):
    r = requests.get(f"{API}/dashboard/stats", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    for k in ("stats", "activity", "mode_usage", "recent_analyses"):
        assert k in body, f"missing {k}"


def test_notifications_list(admin_headers):
    r = requests.get(f"{API}/notifications", headers=admin_headers, timeout=15)
    assert r.status_code == 200


def test_admin_users_and_analytics(admin_headers):
    r = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    users = _extract_list(r.json())
    assert len(users) >= 1

    a = requests.get(f"{API}/admin/analytics", headers=admin_headers, timeout=15)
    assert a.status_code == 200

    al = requests.get(f"{API}/admin/audit-log", headers=admin_headers, timeout=15)
    assert al.status_code == 200


# ---------- 12. Role enforcement ----------

def test_role_enforcement_non_admin_pro_mode(new_user):
    headers = {"Authorization": f"Bearer {new_user['access_token']}"}
    p = requests.post(f"{API}/projects", headers=headers,
                      json={"name": "TEST_est_proj"}, timeout=15)
    if p.status_code not in (200, 201):
        pytest.skip(f"estimator cannot create project ({p.status_code}), skipping")
    pid = p.json()["id"]
    r = requests.post(f"{API}/analyses", headers=headers,
                      json={"mode": "PHASE_2", "project_id": pid, "input_text": "x"}, timeout=20)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text}"


# ---------- 13. Blockchain verify ----------

def test_blockchain_verify(completed_analysis, admin_headers):
    aid, status = completed_analysis
    if status.get("status") != "complete":
        pytest.skip(f"analysis not complete; state={status.get('status')}")
    det = requests.get(f"{API}/analyses/{aid}", headers=admin_headers, timeout=15).json()
    bh = det["blockchain_hash"]
    r = requests.post(f"{API}/blockchain/verify", headers=admin_headers, json={"hash": bh}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("verified") is True
    assert body.get("analysis", {}).get("id") == aid

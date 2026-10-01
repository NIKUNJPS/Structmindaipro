# StructMind AI · Runbook (v4.1.0)

> Everything you need to run, configure, and deploy the platform end-to-end.

---

## PART 1 · What YOU still need to provide

These are the only manual inputs the platform expects from you:

### ① Paste your AI prompts (✅ **DONE** in v4.2.0 — 16 SteelSight modes already wired)
The Detailer and Fabricator roles ship with the full 16-mode SteelSight catalog already integrated into `/app/backend/prompts/`:

| File | Status |
|------|--------|
| `prompts/shared_rules.py` | ✅ 10 baseline output rules — edit if you change the global formatting policy |
| `prompts/detailer_prompts.py` | ✅ All 16 SteelSight modes for Detailer (15 shared + `ESTIMATION_PRO` hours-based) |
| `prompts/fabricator_prompts.py` | ✅ Imports the 15 shared modes + own `FABRICATOR_ESTIMATION_PRO` tonnage-based |
| `prompts/prompt_router.py` | ✅ Wired — no edits needed |

The 15 shared modes are stored as module-level constants in `detailer_prompts.py` and imported into `fabricator_prompts.py`. **Editing a prompt updates both roles automatically.** Only the estimation mode differs (intentional).

**To tweak any prompt:** open the corresponding constant in `detailer_prompts.py` (e.g. `MASTER_INTAKE = """..."""`), edit, restart backend (`sudo supervisorctl restart backend`). Super Admin → Permissions editor will immediately reflect the change.

**To add a brand-new mode:** add a new `NEW_MODE_NAME = """..."""` constant, then add an entry to the `DETAILER_MODES` dict (and the `FABRICATOR_MODES` dict if it should be shared). Restart backend.

---

### ② Production secrets (only needed for live deploy, not preview)
The preview environment already has everything wired. For production, set these in your deployment's environment:

| Variable | Purpose | Where to get it |
|----------|---------|-----------------|
| `MONGO_URL` | Mongo connection string | Mongo Atlas → cluster → Connect → Application |
| `DB_NAME` | Mongo database name | Your choice (e.g. `structmind_prod`) |
| `EMERGENT_LLM_KEY` | AI engine key | Already provisioned for your account |
| `JWT_SECRET` | JWT signing key | Generate: `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First seeded super admin | Your choice |
| `ADMIN_EMAIL_2` / `ADMIN_PASSWORD_2` | Second seeded super admin (optional) | Your choice |
| `RESEND_API_KEY` | **Primary** OTP / email delivery (recommended) | [resend.com](https://resend.com) → API Keys |
| `SMTP_FROM` / `SMTP_FROM_NAME` | Verified sender address + display name | e.g. `noreply@4xstruct.com` / `STRUCTMIND` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | OTP email fallback (used only if `RESEND_API_KEY` is unset) | Gmail App Password, SendGrid, etc. |
| `REACT_APP_BACKEND_URL` (frontend) | Public backend URL | Your deployment URL (e.g. `https://api.4xstruct.com`) |
| `CORS_ORIGINS` (backend) | Comma-separated allowed origins | `https://app.4xstruct.com,https://www.4xstruct.com` |

> 🔐 **NEVER** commit any of these to git. Use your hosting platform's secret manager.

---

### ③ Per-user permission setup (one-time, per user)
After a Detailer/Fabricator signs up (or you create them via Admin → Users → Create User), they land in **lockdown mode** by Plan A defaults:

| Default | Value |
|---------|-------|
| Analyses/month | 10 |
| Max file size | 25 MB |
| Max files per analysis | 3 |
| Allowed modes | **none** (you must enable each one) |
| Allowed exports | markdown, pdf |
| Estimation enabled | Yes for Fabricator, **No for Detailer** |
| Estimation countries | USA only |

To onboard a new user, go to **Admin → Permissions → click "Edit permissions" on their row** and toggle:
- ✅ The specific AI modes they should access
- ✅ Additional export formats (Word, Excel, CSV)
- ✅ Additional countries
- ✅ Feature flags (canSendRfis, canRunEstimation, blockchainAnchoring, etc.)
- ✅ Bump their monthly cap if needed (-1 = unlimited)

Click **Save permissions**. They see the new modes/features on next page reload.

---

## PART 2 · Running locally (development)

```bash
# 1. Clone (or pull) the repo
git clone <your-repo-url> structmind && cd structmind

# 2. Backend — Python 3.11+
cd backend
pip install -r requirements.txt
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
cp .env.example .env       # fill in MONGO_URL, JWT_SECRET, EMERGENT_LLM_KEY, ADMIN_EMAIL/PASSWORD, SMTP_*
# Start the server (uvicorn is in requirements)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 3. Frontend — Node 18+, Yarn
cd ../frontend
yarn install
cp .env.example .env       # set REACT_APP_BACKEND_URL=http://localhost:8001
yarn start                 # opens http://localhost:3000

# 4. Mongo — local dev
docker run -d --name structmind-mongo -p 27017:27017 mongo:7
# Then MONGO_URL=mongodb://localhost:27017
```

After boot, log in with one of the seeded super admins (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).

---

## PART 3 · Deploying to production

The platform is preconfigured to deploy with **one click on Emergent**:

### Option A — Deploy on Emergent (recommended, zero config)
1. Click **"Deploy"** (top-right of the Emergent chat).
2. Pick a subdomain or attach your custom domain (Cloudflare DNS instructions are shown).
3. Set the 4 required secrets in the deploy dialog: `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SMTP_*`.
4. Emergent provisions a Mongo Atlas cluster, sets `MONGO_URL` + `EMERGENT_LLM_KEY` automatically, and ships your build.
5. First request seeds your super admin. Done.

### Option B — Self-host (Vercel + Render + Atlas)
| Layer | Provider | Build command | Start command |
|-------|----------|---------------|---------------|
| Frontend | Vercel | `cd frontend && yarn install && yarn build` | (static) |
| Backend | Render / Railway / Fly | `pip install -r requirements.txt && pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
| Database | Mongo Atlas | n/a | n/a |
| File storage | Persistent disk on backend host (`/data/uploads`) | mount volume | `UPLOAD_DIR=/data/uploads` |

Then point the frontend's `REACT_APP_BACKEND_URL` env to the backend public URL.

> ⚠️ **For self-host**: make sure the backend host has a **persistent disk** mounted at the path you set in `UPLOAD_DIR` — uploaded drawings need to survive deploys (file IDs are referenced by AI extraction).

### Option C — Save to GitHub (CI/CD)
Click **"Save to Github"** in the Emergent chat input. You get a private repo with the full source, and you can wire any CI/CD pipeline you want (GitHub Actions, etc.).

---

## PART 4 · How the AI estimation flow works (end-to-end)

```
USER                       BACKEND                              GEMINI 2.5 PRO
  │                            │                                       │
  ├─ Upload drawing(s) ────────▶ POST /api/files/upload ───────┐       │
  │                            │  (size cap + permission gate) │       │
  │                       store on disk + Mongo (file_id)      │       │
  │  ◀───────── file_id ───────┤                               │       │
  │                            │                               │       │
  ├─ Set LOW & HIGH rates      │                               │       │
  ├─ Click "Analyse"           │                               │       │
  │ ─ POST /api/estimation/ai-calculate ───────────────────────┘       │
  │   { role, rate_low, rate_high, file_ids }                          │
  │                       check perms (canRunEstimation, country, cap) │
  │                       load files from disk                         │
  │                       call STRUCTMIND CORE with role-specific      │
  │                       JSON-extraction prompt + file_contents ─────▶│
  │                                                            extracts:│
  │                                                  Fabricator: tonnage│
  │                                                Detailer: dwgs+cmplx │
  │                       ◀────────────── structured JSON ──────────────│
  │                       apply rate band:                              │
  │                          • Fab: tonnage × rate × (1 + tax_pct)      │
  │                          • Det: dwgs × rate × complexity_mult       │
  │                       persist to estimates collection               │
  │                       write audit_log entry                         │
  │ ◀── { result.visible.grand_low / mid / high, ai_extracted, … } ────┤
  │                                                                    │
  ├─ Click "Download PDF" ──▶ GET /api/estimation/{eid}/pdf ───────────▶│
  │ ◀── application/pdf ──────────────────────────────────────────────┤
```

**Latency**: 8–25 seconds per AI call (depends on file size and Gemini load). Plan UX accordingly — the UI shows a "STRUCTMIND CORE is analysing your drawings…" indicator on the button while it works.

---

## PART 4b · AI analysis engine tuning (`backend/gemini_service.py`)

Large binders are reviewed in small page batches **in parallel**, each batch
falls back across models on its own, and all batches are merged into **one**
report (a lossy merge is rejected and retried; a deterministic section-by-section
merge is the last resort). All knobs are optional env vars:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GEMINI_MODEL_CHAIN` | `gemini-2.5-pro,gemini-3.1-pro-preview,gemini-3.5-flash,gemini-2.5-flash` | Model order. `gemini-2.5-pro` is dropped automatically from 16 Oct 2026 (Google shutdown); any model that returns 404 is skipped for the rest of the process. |
| `GEMINI_MAX_PAGES_PER_BATCH` | `40` | Pages per request. Smaller = more detail per drawing. |
| `GEMINI_MAX_PARALLEL_BATCHES` | `4` | Batches analysed concurrently. Lower it if you hit 429 rate limits. |
| `GEMINI_MEDIA_RESOLUTION` | `high` | `low` / `medium` / `high` / `default` — high reads small dimensions and marks. |
| `GEMINI_MAX_CONTINUATIONS` | `6` | Extra calls when a long report hits the output limit. |
| `GEMINI_MAX_RETRIES` | `3` | Retries on 429 / 5xx / timeouts before falling back to the next model. |
| `GEMINI_REQUEST_TIMEOUT_S` | `900` | Per-call timeout. |
| `GEMINI_MIN_CONSOLIDATION_RATIO` | `0.55` | Merged report must keep at least this share of the partials' content. |

---

## PART 4c · Verified tonnage take-off (`backend/estimation/takeoff.py`)

Tonnage is no longer model arithmetic. The AI lists every member (mark,
profile, qty, length as drawn, sheet); the backend weighs each line:

- **Unit weights** (`estimation/steel_sections.py`): AISC W/S/M/HP/C/MC/WT and metric
  W/UB/UC carry mass in the name; HSS, pipe (ASME B36.10), angles, plates, flats and
  round bars are computed from geometry; IPE/HEA/HEB/UPN/ISMB/ISMC/AU-PFC from catalogue.
- **Lengths** are parsed from the drawing strings (`24'-6 1/2"`, `7468`, `7.468 m`).
- **Double counting**: the same mark on the same sheet counts once; a BOM / member
  schedule quantity overrides plan counts of that mark; the same mark on different
  sheets (typical floors) is counted per sheet.
- **Allowance**: 3% for connection material when not itemised, 1.5% (bolts + welds)
  when plates are itemised — `TAKEOFF_CONNECTION_ALLOWANCE_PCT`,
  `TAKEOFF_BOLT_WELD_ALLOWANCE_PCT`.
- Unweighable lines (missing length/size) are listed as RFI candidates, never guessed.

The same take-off is locked per drawing set and used by MASTER_INTAKE, MTO,
FABRICATOR_ESTIMATION_PRO and `/api/estimation/ai-calculate`; MTO and Master Intake
reports get the full member schedule appended.

---

## PART 5 · Test credentials

**Seeded super admins (auto-created on first boot):**
- `niks.shah236@gmail.com` / `Nikunj@1405`
- `lalit@4xstruct.com` / `Lalit@4xstruct`

Change these via env vars (`ADMIN_EMAIL`, `ADMIN_PASSWORD`, etc.) before your real production deploy.

---

## PART 6 · Common operations

| Operation | How |
|-----------|-----|
| Add a new mode | Edit `prompts/{detailer,fabricator}_prompts.py`, restart backend, enable it per-user via Admin → Permissions |
| Create a user manually | Admin → Users → Create user |
| Reset a user's password | Admin → Users → Reset (icon) next to user row |
| Impersonate a user (read-only, 15 min) | Admin → Users → "View as" — banner appears, all writes blocked, click "Exit impersonation" to return |
| Disable a user | Admin → Users → click Active pill to toggle |
| Inspect what users have done | Admin → Audit Log (filter by user_id or action prefix like `admin.user.`) |
| Run a quick manual estimate (no AI) | `POST /api/estimation/calculate` with full deterministic inputs (Postman/curl) |
| Run an AI estimate | Use the UI at `/estimate` — upload drawings + LOW + HIGH + Calculate |

---

## PART 7 · Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Login works but "/admin/users 403" | User role is detailer/fabricator, not super_admin | Re-seed via env vars or `db.users.updateOne({email}, {$set:{role:"super_admin"}})` |
| AI estimate returns 502 | All Gemini fallback tiers failed | Check `EMERGENT_LLM_KEY` is set; check Emergent → Profile → Universal Key budget |
| "No analysis modes enabled" empty state | Super admin hasn't enabled any modes for that user | Admin → Permissions → toggle modes in AI modes section |
| OTP not arriving | Email provider not configured | Set `RESEND_API_KEY` (+ verified `SMTP_FROM`) in the backend env. With no provider the code logs the OTP to the backend console as a dev fallback; in production a failed send now returns a 502 so the user is told to retry rather than getting a silent "code sent". |
| File upload returns 413 | User's `maxFileSizeMb` cap exceeded | Admin → Permissions → increase Max file size |
| Backend won't start | Bad Mongo URL or missing requirement | `tail -n 100 /var/log/supervisor/backend.err.log` and fix |

---

## PART 8 · File map (where everything lives)

```
/app
├── backend/
│   ├── server.py                       (FastAPI entry · mounts routers · seeds admin)
│   ├── models.py                       (Pydantic models · Role enum locked)
│   ├── permissions.py                  (default + super_admin permissions)
│   ├── security.py                     (JWT, OTP, password hashing, impersonation)
│   ├── seed.py                         (super_admin seeding + legacy role migration)
│   ├── db.py                           (Mongo client + indexes)
│   ├── config.py                       (env loader)
│   ├── gemini_service.py               (STRUCTMIND CORE main analysis runner)
│   ├── middleware/permission_guard.py  (every feature gate lives here)
│   ├── prompts/                        ◀── ★ YOU PASTE YOUR PROMPTS HERE
│   │   ├── shared_rules.py
│   │   ├── detailer_prompts.py
│   │   ├── fabricator_prompts.py
│   │   └── prompt_router.py
│   ├── routes/
│   │   ├── auth.py                     (signup, login, OTP, refresh, password reset)
│   │   ├── admin.py                    (super_admin console API)
│   │   ├── projects.py
│   │   ├── files.py
│   │   ├── analyses.py                 (uses prompt_router + permission_guard)
│   │   ├── rfis.py
│   │   ├── estimation.py               (AI + legacy paths)
│   │   └── platform.py                 (notifications, usage, dashboard stats)
│   └── estimation/
│       ├── ai_extract.py               (calls Gemini, parses JSON extraction)
│       ├── engine.py                   (deterministic + apply_band_to_extracted)
│       ├── rates.py                    (country/currency table)
│       ├── sanity.py                   (estimate sanity check)
│       └── pdf.py                      (dual-mode PDF renderer)
│
├── frontend/src/
│   ├── App.js                          (router · public + protected + admin routes)
│   ├── pages/
│   │   ├── Estimation.jsx              ◀── ★ NEW slimmed AI-driven UI (uploads + LOW + HIGH)
│   │   ├── AnalyzeWizard.jsx           (hides locked modes)
│   │   ├── Dashboard.jsx
│   │   ├── Outputs.jsx · Projects.jsx · …
│   │   └── admin/
│   │       ├── AdminUsers.jsx
│   │       ├── AdminPermissions.jsx
│   │       ├── AdminAuditLog.jsx
│   │       ├── AdminAnalytics.jsx
│   │       └── AdminLayout.jsx
│   ├── hooks/usePermissions.js
│   ├── context/AuthContext.jsx         (login, logout, startImpersonation)
│   └── components/
│       ├── auth/ProtectedRoute.jsx     (AdminRoute checks role==='super_admin')
│       └── layout/AppShell.jsx         (sidebar + topbar + impersonation banner)
│
└── memory/
    ├── PRD.md                          (product status — read first)
    ├── test_credentials.md             (seeded super admin creds)
    └── (this file)
```

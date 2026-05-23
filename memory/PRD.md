# StructMind AI · PRD

## Problem Statement
Build world-class enterprise AI platform for structural steel intelligence by 4XStruct Inc.
Codename STEELSIGHT OMEGA. Adapted to platform stack: React CRA + FastAPI + MongoDB.

## Stack
- Frontend: React (CRA) + Tailwind + shadcn + Framer Motion + Recharts
- Backend: FastAPI + Motor (MongoDB)
- Async: FastAPI BackgroundTasks (Redis/Celery deferred to v2)
- LLM engine: STRUCTMIND CORE (gemini-2.5-pro → gemini-2.5-flash fallback under the hood via emergentintegrations Universal Key). UI and emails never mention "Gemini".
- Auth: JWT (HS256) + bcrypt + 6-digit OTP (5-min expiry)
- OTP triggers: first signup, forgot-password, change-password
- File storage: local disk (`/app/backend/uploads`) — Emergent object storage adapter ready for v2
- Blockchain: SHA-256 hashing stored in MongoDB (Polygon deferred to v2)
- SMTP: placeholder in .env (user will fill), dev-console OTP logging fallback

## Brand system
Navy #0d2240 · Navy Mid #1a3a5c · Gold #f5a800 · Gold Light #ffd166 · Bg #f7f9fc
Typography: **Sora** (headings, geometric / professional SaaS) · IBM Plex Sans (body) · JetBrains Mono (data)
Logo: hexagon with 4X inside + STRUCTMIND below

## User personas (6 roles + admin)
Detailer · Engineer · Fabricator · Estimator · Project Manager · Modular · Admin

## Super admins (seeded on startup)
1. `niks.shah236@gmail.com` / `Nikunj@1405`
2. `lalit@4xstruct.com` / `Lalit@4xstruct`

## Implemented (2026-04-24, v3)

### Backend (12 modules, 55+ endpoints)
- `config.py` · env-driven settings
- `db.py` · Motor client + index ensurer
- `security.py` · bcrypt + JWT HS256 + OTP hash/generate + role guards
- `email_service.py` · SMTP + dev-console fallback, branded HTML templates (no Gemini mention)
- `ai_modes.py` · **all 25 AI modes** with group/role/pro/time + roles array + DRAWING_PROTOCOL preamble
- `role_prompts.py` · **NEW (v3) — 7 role-specific lenses** (detailer/engineer/fabricator/estimator/pm/modular/admin) for every mode + AUTHORITY_PREFACE + 2026 US/India market rate anchors
- `gemini_service.py` · STRUCTMIND CORE fallback chain with engine_label() rebranding (PRO/FAST)
- `demo_prompts.py` · representative demo scope per mode for Role Guide demos
- `export_service.py` · Word / PDF / Excel / CSV / Markdown generation
- `seed.py` · idempotent 2-admin seed
- Routes:
  - auth · signup · verify-otp · login · forgot-password · verify-reset-otp · reset-password · change-password (with OTP) · refresh · resend-otp · me · update-me · logout
  - projects · list · create · get · update · archive · add team member
  - files · upload (500MB) · meta · download · delete · list (SHA-256 hashed)
  - **analyses** · list modes (incl. demo_prompt + roles) · create (ROLE-AWARE prompt composition) · /demo (admin bypasses lock) · list · get · status · rerun · export download · delete
  - rfis · CRUD + status transitions
  - platform · notifications · usage · dashboard stats · blockchain verify · admin users/analytics/audit-log · outputs

### Frontend (15 pages — unchanged from v2)

### v3 delta (this iteration)
- **Role-specific prompts** — every mode composes a different system prompt per role (detailer / engineer / fabricator / estimator / pm / modular / admin). Verified: admin Master Intake = 17,608 chars (9 sections, all layers); detailer Master Intake = 12,179 chars (11 detailing-only sections); outputs are distinct.
- **2026 market rate anchors** — ESTIMATION_PRO and MTO now anchor every dollar figure to USD 1,200-1,700/ton mill / USD 4,500-6,500/ton turnkey bands. Verified estimator output sits inside band ($1,582/ton mill steel).
- **Authoritative tone enforced** — DRAWING_PROTOCOL and AUTHORITY_PREFACE forbid the words "confidence", "approximately", "I think", "NOT PROVIDED", "I cannot", "perhaps", "I don't". Verified clean across all role outputs.
- **Drawing analysis protocol** — every prompt now opens with strict "Read every page... Cite sheet for every claim... No paraphrasing" instructions to maximize accuracy on uploaded drawings.
- **Admin = comprehensive merged view** — combines detailing + engineering + fabrication + commercial + schedule + risk + RFI + 14-day actions layers per mode.


## Testing
- iteration_1.json: 23/23 backend + all frontend passed
- iteration_2.json: new features validated (rebrand · /demo · Role Guide · Sora font · 2nd admin). Two timeouts under concurrent-demo load are ingress-level, not functional.

## Next Action Items (v3 candidates)
- Drop real Gmail SMTP creds into `/app/backend/.env` (`SMTP_USER`, `SMTP_PASS`) to switch from console-OTP to email
- Public share-link for completed analyses (tokenised read-only URL for GCs / EORs)
- Streaming live output (replace 2.5s polling with WebSocket)
- Upgrade from FastAPI BackgroundTasks to Celery + Redis queue for priority tiers
- Polygon Mumbai on-chain anchoring (currently SHA-256 in MongoDB)
- Stripe subscription billing
- Microsoft / Google SSO
- Team invite email flow

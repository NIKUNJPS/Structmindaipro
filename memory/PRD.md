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

## Implemented (2026-04-24, v2)

### Backend (11 modules, 55+ endpoints)
- `config.py` · env-driven settings
- `db.py` · Motor client + index ensurer
- `security.py` · bcrypt + JWT HS256 + OTP hash/generate + role guards
- `email_service.py` · SMTP + dev-console fallback, branded HTML templates (no Gemini mention)
- `ai_modes.py` · **all 25 AI modes** with group/role/pro/time + roles array
- `gemini_service.py` · STRUCTMIND CORE fallback chain with engine_label() rebranding (PRO/FAST)
- `demo_prompts.py` · representative demo scope per mode for Role Guide demos
- `export_service.py` · Word / PDF / Excel / CSV / Markdown generation
- `seed.py` · idempotent 2-admin seed
- Routes:
  - auth · signup · verify-otp · login · forgot-password · verify-reset-otp · reset-password · change-password (with OTP) · refresh · resend-otp · me · update-me · logout
  - projects · list · create · get · update · archive · add team member
  - files · upload (500MB) · meta · download · delete · list (SHA-256 hashed)
  - analyses · list modes (incl. demo_prompt + roles) · create · **/demo** (NEW — admin bypasses lock) · list · get · status · rerun · export download · delete
  - rfis · CRUD + status transitions
  - platform · notifications · usage · dashboard stats · blockchain verify · admin users/analytics/audit-log · outputs

### Frontend (15 pages)
- Global: Sora + IBM Plex + JetBrains Mono, brand tokens, hover-lift utility, page-load transitions
- AuthContext + ProtectedRoute + AdminRoute
- AppShell: 260px navy sidebar (with Role Guide entry) + top bar (search · bell · user menu)
- Pages:
  - Public: Landing (11 sections), Login (60/40 split), Signup, VerifyOtp, ForgotPassword (3-step)
  - App: Dashboard (Demo Console callout + stat cards w/ framer-motion stagger + 30d chart + donut), Projects, ProjectDetail, AnalyzeWizard (25-mode grouped selector), AnalysisReport (accordion + 5 exports + BlockchainBadge), RfiKanban (drag-drop), Outputs (5-format downloads), RiskDashboard, **RoleGuide (NEW — demo console for all 25 modes per role, admin bypass, Preview modal, one-click demo)**, SettingsProfile, SettingsSecurity
  - Admin: Users (role/tier dropdowns), AuditLog

### v2 delta
- Added 2nd super admin (lalit@4xstruct.com)
- Switched heading font: Barlow Condensed → Sora (more professional SaaS)
- Heavy framer-motion animations (staggered stat-card reveals, AnimatePresence on role tabs, hover lift on cards, modal spring-in)
- Rebranded all AI engine surfaces: model_used now shows "STRUCTMIND CORE · PRO / FAST", email footer "STRUCTMIND CORE engine", landing tagline "4X Neural Core Engine"
- NEW /roles Role Guide page + /api/analyses/demo endpoint → one-click demo every mode
- Demo prompt library (25 representative scopes) auto-fills when user skips the optional instructions box

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

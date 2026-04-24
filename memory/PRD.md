# StructMind AI · PRD

## Problem Statement (verbatim from user)
Build world-class enterprise AI platform for structural steel intelligence by 4XStruct Inc.
Codename STEELSIGHT OMEGA. Tech adapted to platform: React CRA + FastAPI + MongoDB + Gemini 2.5 Pro.

## Stack decisions (by user, 2026-04-24)
- Frontend: React (CRA) + Tailwind + shadcn + Framer Motion + Recharts
- Backend: FastAPI + Motor (MongoDB)
- Async: FastAPI BackgroundTasks (Redis/Celery deferred to v2)
- AI: Gemini 2.5 Pro primary via emergentintegrations Universal Key (fallback 2.5-flash → 2.5-flash-lite)
- Auth: JWT (HS256) + bcrypt + 6-digit OTP (5-min expiry)
- OTP triggers: first signup, forgot-password, change-password
- File storage: local disk (`/app/backend/uploads`) — Emergent object storage adapter ready for v2
- Blockchain: SHA-256 hashing stored in MongoDB (Polygon deferred to v2)
- SMTP: placeholder in .env, dev-console OTP logging fallback
- Super admin: niks.shah236@gmail.com / Nikunj@1405 (seeded on startup, role=admin, enterprise tier)

## Brand system
Navy #0d2240 · Navy Mid #1a3a5c · Gold #f5a800 · Gold Light #ffd166 · Bg #f7f9fc
Typography: Barlow Condensed (headings) · IBM Plex Sans (body) · JetBrains Mono (data)
Logo: hexagon with 4X inside + STRUCTMIND below

## What's been implemented (2026-04-24 — v1 MVP)
### Backend (`/app/backend/`)
- `config.py` · env-driven settings
- `db.py` · Motor client + index ensurer
- `security.py` · bcrypt, JWT HS256, OTP generation/hash, role guards
- `email_service.py` · SMTP + dev-console fallback, branded HTML templates (signup, reset, change, password-changed, analysis-complete)
- `ai_modes.py` · **all 25 AI analysis modes** with group/role/pro/time metadata and production prompts
- `gemini_service.py` · Gemini 2.5 Pro → 2.5-flash → 2.5-flash-lite fallback chain via emergentintegrations
- `export_service.py` · Word/PDF/Excel/CSV/Markdown full report generation from markdown blocks
- `seed.py` · idempotent super-admin seeding
- Routes:
  - `auth` · signup, verify-otp, login, forgot-password, verify-reset-otp, reset-password, change-password (with OTP), refresh, resend-otp, me, update-me, logout
  - `projects` · list, create, get, update, archive, add team member
  - `files` · upload (500 MB), meta, download, delete, list (SHA-256 hash stored)
  - `analyses` · list modes, create (BackgroundTask), list, get, status, re-run, export download (docx/pdf/xlsx/csv/md), delete
  - `rfis` · CRUD + status transitions
  - `platform` · notifications, usage, dashboard stats (30-day activity + mode donut), blockchain verify, admin users/analytics/audit-log, outputs listing

### Frontend (`/app/frontend/src/`)
- Global styles: brand colors, 3 fonts, tech-grid + noise classes
- AuthContext + ProtectedRoute + AdminRoute
- AppShell: 260px navy sidebar + top bar (search, bell popover, user menu)
- 14 pages:
  - Landing (11 sections — nav, hero w/ live analysis mockup, trust strip, how-it-works, features, 25-modes grid, personas, comparison, pricing, testimonials, footer)
  - Auth: Login (60/40 split), Signup (split), VerifyOtp, ForgotPassword (3-step)
  - App: Dashboard (stats + 30-day area chart + mode donut + recent analyses), Projects, ProjectDetail, AnalyzeWizard, AnalysisReport, RfiKanban (draggable), Outputs (5-format downloads), RiskDashboard, SettingsProfile, SettingsSecurity (OTP-gated change pw)
  - Admin: Users (role/tier editing), AuditLog

## Next Action Items (P0 for v1 iteration)
- Real Gmail SMTP credentials in .env for OTP email
- Optional: replace placeholder GEMINI_API_KEY with user's own
- Connect team invitations UX to `/api/projects/{id}/team`
- Drag-drop persistence for RFI kanban (server call working; UX polish)

## Backlog (P1)
- Team invite email templates + join flow
- File preview (PDF viewer in browser)
- Chat Assistant mode page (streaming Gemini)
- Real-time WebSocket progress (currently polls every 2.5s)
- Polygon Mumbai on-chain anchoring
- Stripe subscription billing
- Microsoft / Google SSO

## Test credentials
See `/app/memory/test_credentials.md`.

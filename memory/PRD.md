# StructMind AI · Product Requirements (v4.0.0)

## Original problem statement (verbatim)
> Enterprise-grade AI-powered structural-steel intelligence platform for 4XStruct Inc.
> Refactor (Feb 2026): collapse to exactly THREE roles (super_admin, detailer, fabricator),
> introduce granular per-user feature_permissions managed by super_admin, blank prompt
> file scaffolds for user-supplied prompts, full Super Admin panel, and an estimation
> engine restricted to detailer + fabricator (fabricator MUST provide cost_per_ton low/high).

## Architecture (v4.0.0)
- Frontend: React (CRA) + Tailwind + shadcn/ui + Framer Motion
- Backend: FastAPI + Motor (Async MongoDB) + ReportLab (PDF) + Emergent LLM Key (Gemini 2.5)
- Roles (locked at API contract): `super_admin`, `detailer`, `fabricator`
- AI prompts: blank scaffold files (`prompts/shared_rules.py`, `prompts/detailer_prompts.py`,
  `prompts/fabricator_prompts.py`, `prompts/prompt_router.py`) for end-user paste.

## What is implemented (as of 26 Feb 2026 · v4.0.0)
1. **3-Role schema** — `Role` literal locked; legacy 7-role usages purged across backend + frontend.
2. **Seed migration** — Legacy `admin` users auto-upgraded to `super_admin`; legacy `engineer/estimator/pm/modular` auto-migrated to `detailer` so historical records remain attributable.
3. **Granular feature_permissions** (per user, MongoDB collection): analysesPerMonth, maxFileSizeMb, maxFilesPerAnalysis, allowedModes, allowedExports, estimationCountries, plus 10 boolean flags. Defaults are locked-down ("plan A").
4. **Permission Guard middleware** (`/app/backend/middleware/permission_guard.py`): checks mode access, monthly usage, export format, file size, country, and emits audit_log entries.
5. **Super Admin REST API** (`/app/backend/routes/admin.py`):
    - User CRUD + admin password reset
    - Permission read / update
    - Audit log query (filter by action + user)
    - Analytics dashboard (users/projects/analyses/files/RFIs, top modes this month)
    - Modes catalog (`/api/admin/modes/all`)
    - **Impersonation** — 15-min read-only JWT; write endpoints blocked via `block_write_if_readonly`.
6. **Analyses pipeline** wired to `prompts/prompt_router` (replaces deleted `ai_modes.py` / `role_prompts.py` / `demo_prompts.py`) and runs through `permission_guard` for mode + usage + export gating.
7. **Estimation engine** (Detailer + Fabricator only):
    - Detailer = hours × midpoint hourly rate (deterministic).
    - **Fabricator = tonnage × user-provided cost_per_ton_low–high band × composite factor (material × surface × assembly).** Returns a `low → high` range as the headline.
8. **PDF generator** rewritten for both roles with full range presentation on fabricator and proper deliverables list on detailer.
9. **Frontend overhaul**:
    - New `usePermissions` hook (fetches `/api/admin/me/permissions`).
    - `AppShell` shows `Super Admin` nav group only for super_admin and renders an Impersonation banner with `Exit impersonation` button.
    - `/admin/users`, `/admin/permissions(/:uid)`, `/admin/audit-log`, `/admin/analytics` full-feature pages.
    - `AnalyzeWizard` hides locked modes (empty state instead of grayed-out tiles).
    - `Estimation` page highlights Fabricator cost band inputs and shows grand_range_text in the result panel.
    - Signup role dropdown limited to detailer + fabricator.
10. **Legacy files deleted**: `ai_modes.py`, `role_prompts.py`, `demo_prompts.py`, `pages/Admin.jsx`, `pages/RoleGuide.jsx`, stale 7-role tests.

## Testing summary
- Pytest v4 suite: **32/32 passed** (`/app/backend/tests/test_v4_architecture.py`).
- Frontend smoke (Playwright): super_admin login → dashboard → admin/users → admin/permissions → estimate, all routes 200, sidebar shows Platform + Super Admin groups for super_admin only.
- One LOW console warning (Recharts width/height -1) — silenced via `minWidth/minHeight` on `ResponsiveContainer`.

## Default `feature_permissions` for new users (Plan A — locked-down)
```
analysesPerMonth      = 10
maxFileSizeMb         = 25
maxFilesPerAnalysis   = 3
allowedModes          = []                     # super_admin enables explicitly
allowedExports        = ["markdown", "pdf"]
canRunEstimation      = true if fabricator else false
estimationCountries   = ["USA"]
canSendRfis           = false
canViewAuditLog       = false
blockchainAnchoring   = false
```
Super admin holds a wildcard bundle resolved on-the-fly (never persisted).

## P1 / P2 backlog (post-v4 follow-ups)
- **P1** Paste real prompts into `prompts/detailer_prompts.py` & `prompts/fabricator_prompts.py` (currently blank scaffolds with 11 placeholder modes per role).
- **P1** Redis cache for `feature_permissions` lookups (currently 1 mongo hit per request).
- **P1** Polygon anchoring for blockchain hashes (currently SHA-256 ledger in MongoDB).
- **P2** Mode Defaults tab in Admin panel — bulk-apply a permission preset to all detailers / fabricators.
- **P2** Email branding via Resend (currently SMTP/console fallback).
- **P2** RFI inbox with SLA timers + Slack/Teams webhooks.
- **P2** Per-tenant subdomains and white-label.

## Acceptance criteria for v4.0.0 (all met)
- [x] Only 3 roles exist in API/UI; signup rejects others with 422.
- [x] Super admin sees and edits every user's feature_permissions.
- [x] Locked modes are hidden from the analysis wizard, not grayed out.
- [x] Fabricator estimation requires `cost_per_ton_low` and `cost_per_ton_high` (422 otherwise).
- [x] Impersonation token is 15-min and read-only; writes return 403.
- [x] Every admin / estimation / analysis action is recorded in `audit_log`.
- [x] Old 7-role data preserved (migration only; never destructive).

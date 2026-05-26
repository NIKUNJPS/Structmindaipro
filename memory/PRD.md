# StructMind AI · Product Requirements (v4.1.0)

## Original problem statement (verbatim)
> Enterprise-grade AI-powered structural-steel intelligence platform for 4XStruct Inc.
> v4.0.0 Refactor: 3 roles (super_admin, detailer, fabricator), granular feature_permissions, blank prompt scaffolds, Super Admin panel.
> v4.1.0 Update: Collapse both Detailer + Fabricator estimation forms to ONLY {drawing upload, LOW rate, HIGH rate}. AI reads the drawing and produces the quantity → applies the user's rate band → returns a low → high cost range.

## What's new in v4.1.0 (AI-Driven Estimation)
- **Both forms now collapsed to 3 inputs**: drag-drop drawings + `LOW rate` + `HIGH rate` + Calculate.
- **STRUCTMIND CORE (Gemini 2.5 Pro)** extracts:
  - **Fabricator**: total fabricated tonnage (sums BOM weights + 3% accessories)
  - **Detailer**: production drawing count + connection count + complexity grade (Low/Med/High/AESS/Critical) + derived multiplier
- New endpoint: `POST /api/estimation/ai-calculate` (primary; surfaced in UI).
- Legacy endpoint: `POST /api/estimation/calculate` (deterministic; kept for backwards-compat / API users).
- PDF renderer auto-detects the result shape and produces an "AI-EXTRACTED QUANTITIES" section.
- Project name auto-derives from first uploaded file ("AI · bom.csv").
- Detailer rate semantics changed: was `per-hour`, now `per-drawing`.

## Architecture (unchanged from v4.0.0)
- Frontend: React (CRA) + Tailwind + shadcn/ui + Framer Motion
- Backend: FastAPI + Motor (async MongoDB) + ReportLab (PDF) + Emergent LLM Key (Gemini 2.5 Pro / Flash fallback)
- Roles: `super_admin`, `detailer`, `fabricator`

## What is implemented (cumulative)
1. **3-Role schema** + legacy migration on startup.
2. **Granular feature_permissions** per user (Plan A locked-down defaults).
3. **Permission Guard middleware** (mode, usage, export, file-size, country gates + audit log).
4. **Super Admin REST API** (user CRUD, password reset, permission editor, audit log query, analytics, modes catalog, 15-min read-only impersonation).
5. **Analyses pipeline** wired to `prompts/prompt_router` + permission guard.
6. **Estimation engine**:
   - AI-driven (`/ai-calculate`) — drawing + LOW + HIGH only (PRIMARY UI flow)
   - Deterministic (`/calculate`) — full manual inputs (API / power users)
7. **PDF generator** dual-mode (deterministic + AI-driven).
8. **Frontend overhaul**: Super Admin Console (Users / Permissions / Audit Log / Analytics), AnalyzeWizard hides locked modes, drawing-driven Estimation page, signup restricted to detailer/fabricator.

## Testing summary
- **iteration_3**: 32/32 backend pytest pass (v4.0.0 3-role architecture).
- **iteration_4**: 20/20 backend pytest pass (v4.1.0 AI estimation) + frontend smoke 100%.
- Cumulative: 52/52 backend tests passing.

## P1 / P2 backlog (post-v4.1.0)
- **P1** Paste real prompt content into `prompts/detailer_prompts.py` & `prompts/fabricator_prompts.py` (currently blank scaffolds with 11 placeholder modes per role).
- **P1** Redis cache for `feature_permissions`.
- **P1** Polygon anchoring for blockchain hashes.
- **P2** Mode Defaults tab — bulk-apply preset to all detailers/fabricators.
- **P2** Resend email branding.
- **P2** RFI SLA timers + Slack/Teams webhooks.
- **P2** Per-tenant subdomains and white-label.
- **P2** AI estimation: support .dwg/.dxf vector → raster pre-conversion for richer extraction.

## Acceptance criteria for v4.1.0 (all met)
- [x] Both forms collapsed to drawing upload + LOW + HIGH + Calculate.
- [x] AI extracts quantity from real uploaded drawing (verified with BOM: 14.9 t / 5 drawings).
- [x] Output is a deterministic low → high range driven by user's rate band.
- [x] All legacy manual fields hidden in UI.
- [x] PDF download works for both modes.
- [x] Estimation locked behind `canRunEstimation` permission with friendly 403.
- [x] Country lockdown enforced.
- [x] File count cap enforced.
- [x] Audit log entry written on every AI call.

"""Representative demo scope prompts for every AI mode.
Used by /api/analyses (when input_text is empty) and /api/analyses/demo
to showcase role-locked modes without real drawings.
"""
from __future__ import annotations

DEMO_PROMPTS: dict[str, str] = {
    "MASTER_INTAKE": (
        "Representative scope: a mid-size US steel fabrication project — 3-storey office "
        "tower in Denver CO, ~220 tons of structural steel, W-shapes A992 Gr50, HSS braces, "
        "base plates on 5'-6' anchor bolts, shear tab + moment end-plate connections, "
        "AESS Category 2 on lobby columns, SSPC paint system. Deliver a full Master Intake audit."
    ),
    "PHASE_1": (
        "Scope for Phase-1: drawing package S-001 through S-412, architectural A-0 series, "
        "anchor bolt plan, base-plate schedule, column grid 1–8 / A–G. 3-storey office tower, "
        "220 tons. Extract the drawing index, scope summary and anchor schedule."
    ),
    "PHASE_2": (
        "Representative connection set: moment end-plates at gridlines 3-C, 3-F and 6-C; "
        "shear tab connections throughout interior bays; HSS X-braces on perimeter; bolt "
        "group 7/8\" A490 SC; welds per AWS D1.1 prequalified CJP. Seismic Design Category C. "
        "Audit all connection types with exact AISC 360-22 clause citations."
    ),
    "PHASE_3": (
        "Produce a Phase-3 fabrication & cost workup for a 220-ton 3-storey steel-frame "
        "office building. Assume US Midwest fabricator, dual-burn + robot welding, SSPC-SP6 "
        "+ 3-coat epoxy/urethane paint, truck delivery to Denver CO."
    ),
    "SUMMARY": (
        "Representative scope: a 220-ton, 3-storey steel-frame office tower in Denver CO with "
        "moment frames at core, HSS braced perimeter, AESS lobby columns. Produce a one-page "
        "executive summary."
    ),
    "DRAWING_CHECKER": (
        "Assume you have been sent shop-drawing set SD-Rev-B covering columns (piece marks "
        "C01-C48), beams (B01-B186), braces (HSB01-HSB24) and misc metals. Run a full Drawing "
        "Checker QC against AISC 360-22, AWS D1.1, ASTM and SSPC. Report Critical / Major / "
        "Minor findings with clause references."
    ),
    "ISSUE_DETECTOR": (
        "Representative mid-size steel-frame project with moment frames, bracing, base plates "
        "and miscellaneous metals. Produce a prioritised issues table (at least 12 rows)."
    ),
    "CNC_FILE_CHECKER": (
        "Assume NC1 files for piecemarks C01 (W14x99 × 12'-0\", 4 holes per base plate), "
        "B15 (W18x35 × 28'-6\", shear tab clip 5/8\" A325), HSB04 (HSS6x6x3/8 × 14'-9\" with "
        "gusset copes). Review file-to-drawing piecemark alignment, hole patterns, cope/notch "
        "geometry and fabrication readiness."
    ),
    "STRUCTURAL_CLASH_DETECTOR": (
        "Representative 3D model: steel skeleton across 8×7 grid, 3 levels. Check for "
        "member-to-member hard clashes, soft clearance violations, MEP interferences on "
        "level-2 mechanical room, and tool/bolt clearance at moment end-plate connections."
    ),
    "SPEC_COMPLIANCE_AUDITOR": (
        "Audit full code compliance (AISC 360-22, AISC 341, AWS D1.1 & D1.8, RCSC, ASTM, SSPC, "
        "OSHA 1926 Subpart R) for a 3-storey 220-ton steel-frame office building with SDC C."
    ),
    "MTO": (
        "220-ton 3-storey steel-frame project. Members: ~48 columns (W14x90–W14x132), "
        "~186 beams (W14x22–W18x40), ~24 HSS braces, base plates (1-1/2\" A572-50), "
        "shear tabs, end plates, 7/8\" A490 bolts. Produce full MTO with weights and totals."
    ),
    "PROCUREMENT_PACKAGE": (
        "Generate a ready-to-send procurement package for 220 tons of structural steel, "
        "50 plates (various), ~3200 bolts (A325 & A490), ~28 kg weld wire, SSPC paint system. "
        "US Midwest mill preferred, 6-week lead-time target."
    ),
    "ESTIMATION_PRO": (
        "Estimate a 220-ton steel-frame project (Denver CO). Include material, labour, "
        "equipment, consumables, freight and coatings. Deliver Estimation Pro with "
        "sensitivity analysis on steel price ±10%, labour ±10% and schedule ±2 weeks. "
        "Recommend a bid price range."
    ),
    "BID_STRATEGY": (
        "You are advising on a competitive bid for a 220-ton 3-storey steel tower in Denver. "
        "Three known competitors are bidding. Provide a bid-strategy memo with win-likelihood, "
        "risk register, qualifications, commercial terms and Go/No-Go recommendation."
    ),
    "VALUE_ENGINEERING": (
        "Given a 220-ton steel-frame design, identify the top 10 value-engineering "
        "opportunities, connection simplifications, grade/profile substitutions and schedule "
        "compression ideas."
    ),
    "CHANGE_ORDER_GENERATOR": (
        "Two detected scope changes: (1) owner added a 24'×48' mezzanine at level-2 (~12 tons); "
        "(2) AESS category upgraded from 2 to 3 on lobby. Draft Change Orders with cost, "
        "schedule impact and owner-approval blocks."
    ),
    "DRAWING_SUBMISSION_SCHEDULE": (
        "Produce a drawing submission schedule for a 220-ton steel-frame project with 412 "
        "shop drawings organised into 6 packages (anchor bolts, columns, beams, braces, "
        "misc metals, stairs/rails)."
    ),
    "INTERNAL_SCHEDULE_PLANNER": (
        "Create an internal detailer → fabricate → paint → deliver → erect schedule for a "
        "220-ton 3-storey steel-frame project. Erection starts T+12 weeks from award."
    ),
    "SUBMITTAL_TRACKER": (
        "Track submittals for 6 packages (anchor bolts Rev C, columns Rev B, beams Rev A, "
        "braces Rev A, misc Rev 0, stairs Rev 0). Some stamped Approved as Noted, some "
        "Revise & Resubmit."
    ),
    "LANDSCAPE_SPECIALIST": (
        "Site steel scope for the same Denver project: canopy over main entry, trellis over "
        "outdoor dining terrace, handrails / guardrails at roof terrace, bollards at loading. "
        "Specialist review for misc metals + coatings."
    ),
    "POST_AWARD_RISK_TRACKER": (
        "You are 4 weeks into a 220-ton steel project. Produce a post-award risk tracker "
        "with active risks, heat-map, mitigation actions and a top-3 escalation list."
    ),
    "SUSTAINABILITY_REPORT": (
        "Deliver a sustainability report for 220 tons of structural steel (EAF mills vs BOF), "
        "SSPC 3-coat paint system, truck delivery 900 mi. Include embodied-carbon estimate and "
        "LEED MRc contribution."
    ),
    "SAFETY_PLAN": (
        "Write a lifting, rigging and erection safety plan for the 3-storey steel erection "
        "(crane radius 70 ft, heaviest pick = 4.2 tons spandrel girder). OSHA 1926 Subpart R."
    ),
    "CONNECTION_DESIGN_ADVISOR": (
        "For a 3-storey SMF + OCBF mixed system, recommend optimal connection types across "
        "beam-column interior joints, beam-column exterior joints, column base plates, "
        "brace-to-gusset and splice connections. Cite governing AISC 360-22 limit states."
    ),
    "CHAT_ASSISTANT": (
        "What connection type do you recommend for a W18x40 beam framing into the flange of a "
        "W14x90 column in a 3-storey OCBF frame, SDC C? Reference AISC provisions."
    ),
}


def get_demo_prompt(mode_id: str) -> str:
    return DEMO_PROMPTS.get(
        mode_id,
        "Run this mode against a representative mid-size structural steel fabrication scope.",
    )

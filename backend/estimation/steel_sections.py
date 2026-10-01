"""Deterministic steel section unit weights (kg/m) and length parsing.

The model reads the drawings; this module does the arithmetic. Every unit
weight is either read from the designation itself (AISC W/S/M/HP/C/MC/WT and
metric W/UB/UC/PFC carry their mass in the name), computed from geometry
(HSS, pipe, angles, plates, flats, round bars) or looked up in a catalogue
(IPE / HEA / HEB / ISMB / ISMC / Australian PFC). Nothing is guessed.

Steel density: 7 850 kg/m³ (= 490 lb/ft³).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

DENSITY_KG_M3 = 7850.0
LBFT_TO_KGM = 1.488164          # 1 lb/ft = 1.488164 kg/m
IN_TO_MM = 25.4
LB_PER_FT_PER_IN2 = 3.4028      # steel: weight (lb/ft) per in² of area


@dataclass(frozen=True)
class SectionWeight:
    kg_per_m: float
    family: str          # e.g. "W", "HSS-RECT", "PLATE"
    source: str          # "designation" | "geometry" | "catalogue"
    normalized: str      # canonical designation


# ─────────────────────────────────────────────────────────────────────────────
# Catalogues (kg/m) — only for families whose mass is not in the designation
# ─────────────────────────────────────────────────────────────────────────────

IPE = {80: 6.0, 100: 8.1, 120: 10.4, 140: 12.9, 160: 15.8, 180: 18.8, 200: 22.4,
       220: 26.2, 240: 30.7, 270: 36.1, 300: 42.2, 330: 49.1, 360: 57.1, 400: 66.3,
       450: 77.6, 500: 90.7, 550: 106.0, 600: 122.0}
HEA = {100: 16.7, 120: 19.9, 140: 24.7, 160: 30.4, 180: 35.5, 200: 42.3, 220: 50.5,
       240: 60.3, 260: 68.2, 280: 76.4, 300: 88.3, 320: 97.6, 340: 105.0, 360: 112.0,
       400: 125.0, 450: 140.0, 500: 155.0, 550: 166.0, 600: 178.0, 650: 190.0,
       700: 204.0, 800: 224.0, 900: 252.0, 1000: 272.0}
HEB = {100: 20.4, 120: 26.7, 140: 33.7, 160: 42.6, 180: 51.2, 200: 61.3, 220: 71.5,
       240: 83.2, 260: 93.0, 280: 103.0, 300: 117.0, 320: 127.0, 340: 134.0,
       360: 142.0, 400: 155.0, 450: 171.0, 500: 187.0, 550: 199.0, 600: 212.0,
       650: 225.0, 700: 241.0, 800: 262.0, 900: 291.0, 1000: 314.0}
UPN = {80: 8.64, 100: 10.6, 120: 13.4, 140: 16.0, 160: 18.8, 180: 22.0, 200: 25.3,
       220: 29.4, 240: 33.2, 260: 37.9, 280: 41.8, 300: 46.2, 320: 59.5, 350: 60.6,
       380: 63.1, 400: 71.8}
# IS 808 (India)
ISMB = {100: 11.5, 125: 13.0, 150: 14.9, 175: 19.3, 200: 25.4, 225: 31.2, 250: 37.3,
        300: 44.2, 350: 52.4, 400: 61.6, 450: 72.4, 500: 86.9, 550: 103.7, 600: 122.6}
ISMC = {75: 6.8, 100: 9.2, 125: 12.7, 150: 16.4, 175: 19.1, 200: 22.1, 225: 25.9,
        250: 30.4, 300: 35.8, 350: 42.1, 400: 49.4}
# AS/NZS 3679.1 parallel flange channels (designation carries depth only)
AU_PFC = {75: 5.92, 100: 8.33, 125: 11.9, 150: 17.7, 180: 20.9, 200: 22.9, 230: 25.1,
          250: 35.5, 300: 40.1, 380: 55.2}

# ASME B36.10 nominal pipe: NPS → (OD in, {schedule: wall in})
PIPE = {
    "1/2":   (0.840,  {"STD": 0.109, "XS": 0.147, "XXS": 0.294}),
    "3/4":   (1.050,  {"STD": 0.113, "XS": 0.154, "XXS": 0.308}),
    "1":     (1.315,  {"STD": 0.133, "XS": 0.179, "XXS": 0.358}),
    "1-1/4": (1.660,  {"STD": 0.140, "XS": 0.191, "XXS": 0.382}),
    "1-1/2": (1.900,  {"STD": 0.145, "XS": 0.200, "XXS": 0.400}),
    "2":     (2.375,  {"STD": 0.154, "XS": 0.218, "XXS": 0.436}),
    "2-1/2": (2.875,  {"STD": 0.203, "XS": 0.276, "XXS": 0.552}),
    "3":     (3.500,  {"STD": 0.216, "XS": 0.300, "XXS": 0.600}),
    "3-1/2": (4.000,  {"STD": 0.226, "XS": 0.318}),
    "4":     (4.500,  {"STD": 0.237, "XS": 0.337, "XXS": 0.674}),
    "5":     (5.563,  {"STD": 0.258, "XS": 0.375, "XXS": 0.750}),
    "6":     (6.625,  {"STD": 0.280, "XS": 0.432, "XXS": 0.864}),
    "8":     (8.625,  {"STD": 0.322, "XS": 0.500, "XXS": 0.875}),
    "10":    (10.750, {"STD": 0.365, "XS": 0.500, "XXS": 1.000}),
    "12":    (12.750, {"STD": 0.375, "XS": 0.500, "XXS": 1.000}),
}


# ─────────────────────────────────────────────────────────────────────────────
# Number parsing
# ─────────────────────────────────────────────────────────────────────────────

_NUM = r"\d+(?:\.\d+)?(?:[-\s]\d+/\d+)?|\d+/\d+"


def parse_number(text: str) -> float | None:
    """'3/8' → 0.375, '1-1/2' → 1.5, '1 1/2' → 1.5, '12.7' → 12.7."""
    if text is None:
        return None
    s = str(text).strip().replace("″", "").replace('"', "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)?[-\s]?(?:(\d+)/(\d+))?", s)
    if not m or not (m.group(1) or m.group(2)):
        return None
    whole = float(m.group(1)) if m.group(1) else 0.0
    if m.group(2):
        den = float(m.group(3))
        if den == 0:
            return None
        whole += float(m.group(2)) / den
    return whole


def _nums(body: str) -> list[float] | None:
    parts = [p for p in re.split(r"\s*[xX×*]\s*", body.strip()) if p]
    vals = [parse_number(p) for p in parts]
    return None if any(v is None for v in vals) else vals  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Geometry
# ─────────────────────────────────────────────────────────────────────────────

def _rect_tube_area(b: float, h: float, t: float, r_out: float) -> float:
    """Area of a rectangular hollow section with outside corner radius r_out."""
    r_in = max(r_out - t, 0.0)
    return 2 * t * (b + h - 4 * r_out) + math.pi * (r_out ** 2 - r_in ** 2)


def _mm2_to_kgm(area_mm2: float) -> float:
    return area_mm2 * 1e-6 * DENSITY_KG_M3


def _in2_to_kgm(area_in2: float) -> float:
    return area_in2 * LB_PER_FT_PER_IN2 * LBFT_TO_KGM


def _metric_corner_radius(t: float) -> float:
    # EN 10219 cold-formed outside corner radius
    return 2.0 * t if t <= 6 else 2.5 * t if t <= 10 else 3.0 * t


# ─────────────────────────────────────────────────────────────────────────────
# Designation → unit weight
# ─────────────────────────────────────────────────────────────────────────────

def _clean(profile: str) -> str:
    s = (profile or "").upper().strip()
    s = s.replace("×", "X").replace("*", "X")
    s = re.sub(r"\s*X\s*", "X", s)
    s = re.sub(r"\s+", " ", s)
    return s


def unit_weight(profile: str, units: str = "auto") -> SectionWeight | None:
    """Return the unit weight (kg/m) for a section designation, or None if
    the designation is not recognised. Plates/flats return kg/m of length
    for the stated thickness × width."""
    s = _clean(profile)
    if not s:
        return None
    compact = s.replace(" ", "")

    # ── AISC / metric rolled shapes with mass in the designation ────────────
    m = re.fullmatch(r"(W|S|M|HP|C|MC|WT|MT|ST)(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", compact)
    if m:
        fam, depth, mass = m.group(1), float(m.group(2)), float(m.group(3))
        imperial_max_depth = {"W": 44, "S": 24, "M": 12.5, "HP": 18, "C": 15,
                              "MC": 18, "WT": 22, "MT": 6.5, "ST": 12}[fam]
        if depth > imperial_max_depth:          # metric designation, kg/m
            return SectionWeight(mass, fam, "designation", f"{fam}{m.group(2)}x{m.group(3)}")
        return SectionWeight(round(mass * LBFT_TO_KGM, 3), fam, "designation",
                             f"{fam}{m.group(2)}x{m.group(3)}")

    # UK / EU UB, UC, PFC:  UB457X191X67, UC254X254X73, PFC200X90X30
    m = re.fullmatch(r"(UB|UC|PFC|UBP|RSJ|TUB|TUC)(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", compact)
    if m:
        return SectionWeight(float(m.group(4)), m.group(1), "designation", s)

    # Australian 460UB67.1, 310UC137
    m = re.fullmatch(r"(\d+)(UB|UC|WB|WC)(\d+(?:\.\d+)?)", compact)
    if m:
        return SectionWeight(float(m.group(3)), m.group(2), "designation", s)
    m = re.fullmatch(r"(\d+)PFC", compact)
    if m and int(m.group(1)) in AU_PFC:
        return SectionWeight(AU_PFC[int(m.group(1))], "PFC", "catalogue", s)

    # European / Indian catalogue shapes
    for fam, table in (("IPE", IPE), ("HEA", HEA), ("HE A", HEA), ("HEB", HEB),
                       ("HE B", HEB), ("UPN", UPN), ("ISMB", ISMB), ("ISMC", ISMC)):
        fam_c = fam.replace(" ", "")
        m = re.fullmatch(rf"{fam_c}(\d+)", compact) or re.fullmatch(rf"(\d+){fam_c}", compact)
        if m and int(m.group(1)) in table:
            return SectionWeight(table[int(m.group(1))], fam_c, "catalogue", f"{fam_c}{m.group(1)}")

    # ── Hollow sections ─────────────────────────────────────────────────────
    m = re.fullmatch(r"(HSS|SHS|RHS|TS)(.+)", compact)
    if m:
        fam, vals = m.group(1), _nums(m.group(2))
        if vals and len(vals) == 3:
            b, h, t = vals
            metric = units == "metric" or b > 32 or fam in ("SHS", "RHS")
            if metric:
                # CSA / AISC-style "HSS" uses r = 2t; EN / AS "SHS"/"RHS" use EN 10219 radii.
                r_out = 2 * t if fam in ("HSS", "TS") else _metric_corner_radius(t)
                area = _rect_tube_area(b, h, t, r_out)
                return SectionWeight(round(_mm2_to_kgm(area), 3),
                                     "HSS-RECT", "geometry", f"{fam}{vals[0]:g}x{vals[1]:g}x{vals[2]:g}")
            area = _rect_tube_area(b, h, t, 2 * t)   # AISC: nominal t, r = 2t
            return SectionWeight(round(_in2_to_kgm(area), 3), "HSS-RECT", "geometry", s)
        if vals and len(vals) == 2:                    # round HSS: HSS6.625X0.280
            d, t = vals
            metric = units == "metric" or d > 32
            if metric:
                return SectionWeight(round(_mm2_to_kgm(math.pi * t * (d - t)), 3),
                                     "HSS-ROUND", "geometry", s)
            return SectionWeight(round(_in2_to_kgm(math.pi * t * (d - t)), 3),
                                 "HSS-ROUND", "geometry", s)

    m = re.fullmatch(r"(CHS|PIPE|OD)(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", compact)
    if m and float(m.group(2)) > 30:                  # metric CHS d × t (mm)
        d, t = float(m.group(2)), float(m.group(3))
        return SectionWeight(round(_mm2_to_kgm(math.pi * t * (d - t)), 3), "CHS", "geometry", s)

    # AISC pipe: PIPE6STD, PIPE 6 XS, PIPE1-1/2XXS, P6STD
    m = re.fullmatch(r"(?:PIPE|P)\s?(\d+(?:-\d+/\d+)?|\d+/\d+)\s?(STD|XS|XH|XXS|XXH|SCH40|SCH80|S40|S80)?", s)
    if m and m.group(1) in PIPE:
        sched = (m.group(2) or "STD").replace("XH", "XS").replace("XXH", "XXS")
        sched = {"SCH40": "STD", "S40": "STD", "SCH80": "XS", "S80": "XS"}.get(sched, sched)
        od, walls = PIPE[m.group(1)]
        if sched in walls:
            t = walls[sched]
            lbft = 10.69 * (od - t) * t                # ASME B36.10 weight formula
            return SectionWeight(round(lbft * LBFT_TO_KGM, 3), "PIPE", "geometry",
                                 f"PIPE{m.group(1)}{sched}")

    # ── Angles: L4X4X1/2, L100X100X10, ISA75X75X6, EA100X100X8, UA… ─────────
    m = re.fullmatch(r"(L|ISA|EA|UA|RSA|LLH|LLV|2L)(.+)", compact)
    if m:
        vals = _nums(m.group(2))
        if vals and len(vals) == 3:
            a, b, t = vals
            pair = 2 if m.group(1) == "2L" else 1
            metric = units == "metric" or a > 12 or m.group(1) in ("ISA", "EA", "UA", "RSA")
            area = t * (a + b - t)
            kgm = _mm2_to_kgm(area) if metric else _in2_to_kgm(area)
            return SectionWeight(round(kgm * pair, 3), "ANGLE", "geometry", s)

    # ── Plates / flats / bars ───────────────────────────────────────────────
    m = re.fullmatch(r"(PL|PLATE|FL|FB|FLAT|BAR)(.+)", compact)
    if m:
        vals = _nums(m.group(2))
        if vals and len(vals) >= 2:
            t, w = vals[0], vals[1]
            if t > w:
                t, w = w, t
            metric = units == "metric" or w > 48 or (units == "auto" and t >= 3 and "/" not in m.group(2))
            area = t * w
            kgm = _mm2_to_kgm(area) if metric else _in2_to_kgm(area)
            return SectionWeight(round(kgm, 4), "PLATE", "geometry", s)

    m = re.fullmatch(r"(RD|RB|ROD|ROUND|Ø|DIA)(\d+(?:\.\d+)?(?:-\d+/\d+)?|\d+/\d+)", compact)
    if m:
        d = parse_number(m.group(2)) or 0
        metric = units == "metric" or d > 6
        area = math.pi * d * d / 4
        kgm = _mm2_to_kgm(area) if metric else _in2_to_kgm(area)
        return SectionWeight(round(kgm, 4), "ROUND-BAR", "geometry", s)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Lengths
# ─────────────────────────────────────────────────────────────────────────────

def parse_length_mm(raw, units: str = "auto") -> float | None:
    """Parse a drawing length into millimetres.

    Accepts 24'-6", 24' 6 1/2", 24'-0", 7'-9 5/8", 18', 6", 7468, 7468 mm,
    7.468 m, 7468.0. Bare numbers are mm for metric projects, and also mm when
    > 100 on 'auto'; on imperial projects bare numbers ≤ 100 are feet.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        if units == "imperial" and val <= 100:
            return val * 304.8
        return val if val > 0 else None
    s = str(raw).strip().lower().replace("’", "'").replace("′", "'").replace("”", '"').replace("″", '"')
    s = s.replace("''", '"')
    if not s:
        return None

    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*'\s*-?\s*(?:(\d+(?:\.\d+)?)?\s*(?:[-\s]?(\d+)/(\d+))?\s*\"?)?", s)
    if m and "'" in s:
        feet = float(m.group(1))
        inches = float(m.group(2)) if m.group(2) else 0.0
        if m.group(3):
            inches += float(m.group(3)) / float(m.group(4))
        return feet * 304.8 + inches * IN_TO_MM
    m = re.fullmatch(r"(\d+(?:\.\d+)?)?\s*(?:[-\s]?(\d+)/(\d+))?\s*(\"|in|inch|inches)", s)
    if m and (m.group(1) or m.group(2)):
        inches = float(m.group(1) or 0)
        if m.group(2):
            inches += float(m.group(2)) / float(m.group(3))
        return inches * IN_TO_MM
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mm|m|ft)?", s.replace(",", ""))
    if m:
        val, unit = float(m.group(1)), m.group(2)
        if unit == "mm":
            return val
        if unit == "m":
            return val * 1000
        if unit == "ft":
            return val * 304.8
        if units == "imperial" and val <= 100:
            return val * 304.8
        return val
    return None

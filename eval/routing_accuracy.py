"""Day 1 gate. 50 labelled complaints. Under ~80% and the table widens tonight.

Owner: Alakshendra
Lane: institutions

WHAT THIS MEASURES, AND WHAT IT DOES NOT
----------------------------------------
It measures the jurisdiction table's coverage and the routing rule: given a
complaint, does the system name the responsible body, and does it decline to
guess when the table has no entry.

It does NOT yet measure the extraction. The default extractor here is keyword
matching over the curated aliases, and the corpus below was hand-labelled by
the same person on the same afternoon -- so a high score says the table is
wide enough, not that the NLU works. `evaluate()` takes the extractor as an
argument so that when intake lands, the real model call swaps in on one line
and the number starts meaning the harder thing.

Three complaints below are deliberately written the way people actually write
them -- abbreviated, misspelt, unspaced -- and the alias list does not cover
them. They are labelled with the true authority, so they count as failures.
A gate that cannot fail is not a gate.

Run: python -m eval.routing_accuracy
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

from agents.remedy import resolve, segment_aliases
from core.types import Claim, Service

TARGET = 0.80

BWSSB = "BWSSB"
BBMP = "BBMP"
GREEN_MEADOWS = "Green Meadows Layout developer (internal line, pre-handover)"
SUNRISE = "Sunrise Enclave developer (internal line, pre-handover)"
BROOKEFIELD = "Brookefield Extension developer (internal line, pre-handover)"

# Checked in order. Non-water first, because "dirty water on the street" is a
# blocked drain and "water" is the last word that should decide it.
SERVICE_KEYWORDS: list[tuple[Service, tuple[str, ...]]] = [
    (Service.GARBAGE, ("garbage", "waste collection", "kasa", "dump")),
    (Service.ROADS, ("pothole", "road is broken", "road dug", "tar")),
    (Service.STREETLIGHT, ("street light", "streetlight", "light not working", "lamp")),
    (Service.SEWAGE, ("sewage", "drain", "manhole", "ugd", "gutter")),
    (Service.WATER, ("water", "neeru", "supply", "tap", "tanker", "borewell",
                     "cauvery", "sump", "pipeline", "pressure")),
]


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def keyword_extract(text: str) -> tuple[Service | None, str]:
    """Stand-in for the intake model. Returns (service, segment).

    Note what it does NOT return: feeder_id. A citizen never writes "trunk main
    14" -- the feeder comes from the household's onboarding record, not from
    the complaint. Passing an empty feeder is the honest thing here.
    """
    flat = normalise(text)

    service = None
    for candidate, keywords in SERVICE_KEYWORDS:
        if any(k in flat for k in keywords):
            service = candidate
            break

    segment = ""
    # Longest alias first: "4th cross road" must win over "4th cross".
    for alias in sorted(segment_aliases(), key=len, reverse=True):
        if alias in flat:
            segment = segment_aliases()[alias]
            break

    return service, segment


# ---------------------------------------------------------------------------
# 50 complaints, hand-labelled. `None` means the correct behaviour is to say
# we do not know and ask -- the table covers water in Ward 12 and nothing else,
# so a pothole or an uncurated street SHOULD come back unresolved. Filing those
# somewhere plausible is the failure this project exists to fix.
# ---------------------------------------------------------------------------

COMPLAINTS: list[tuple[str, str | None]] = [
    # -- BWSSB trunk mains -------------------------------------------------
    ("Three days aaytu, no water at all in 4th Cross. Tank is empty, RR 1122334.", BWSSB),
    ("Water supply completely stopped since Monday on 5th Cross road, whole street affected.", BWSSB),
    ("No Cauvery water 3rd cross since two days. Please help.", BWSSB),
    ("Temple street here, taps dry from Sunday, we are buying tanker daily.", BWSSB),
    ("Ward 12 main road, water coming only 20 minutes and very low pressure.", BWSSB),
    ("6th main, pipeline burst near the corner, water going waste since morning.", BWSSB),
    ("7th main road, muddy water coming from tap for last three days.", BWSSB),
    ("8th Main Rd. no supply. Neighbours also complaining same.", BWSSB),
    ("Lake view road, water supply is irregular, coming once in three days only.", BWSSB),
    ("1st stage, no water since Friday. Two flats sharing one tanker.", BWSSB),
    ("2nd stage, supply stopped, valve man says pipeline work but no information.", BWSSB),
    ("3rd stage, water not coming at all. RR 5566778.", BWSSB),
    ("School street, taps dry since two days, children unable to bathe before school.", BWSSB),
    ("Hospital road, very low pressure, water not reaching first floor.", BWSSB),
    ("Station road, no water supply for five days, please arrange.", BWSSB),
    ("Market road here, water is smelling badly, cannot use for cooking.", BWSSB),
    ("Bus-stand road, supply stopped after the road work last week.", BWSSB),
    ("Post office lane, no water since Wednesday, entire lane affected.", BWSSB),
    ("Library road, water coming at 2am only for 10 minutes.", BWSSB),
    ("Mill road, no water supply, we have been calling the helpline with no response.", BWSSB),
    ("Factory lane, pipeline leaking for a week, still no supply in houses.", BWSSB),
    ("Depot road, water not coming since three days, 12 houses affected.", BWSSB),
    ("Again no water on 4th cross, this is the fourth time since June.", BWSSB),
    ("Godown street, dry taps, duration four days, affected houses around eight.", BWSSB),

    # Written the way people write. The alias list does not cover these three.
    ("No water 4th crs since 2 days pls look into it", BWSSB),
    ("Neeru illa on 6th mn road since two days, tanker also not coming", BWSSB),
    ("Parkextension no water for four days now, sump is fully empty", BWSSB),

    # -- BBMP borewell, absorbed village ------------------------------------
    # The right answer here is NOT the one the citizen assumes, and that is the
    # whole reason the lookup is grounded.
    ("Old village area, borewell not working since two days, no water at all.", BBMP),
    ("Kere mohalla, water not coming. BWSSB people are saying it is not their area.", BBMP),
    ("Gundu thope lane, the borewell motor burnt, whole street without water.", BBMP),
    ("Hale ooru side no water for three days, ward number 12.", BBMP),
    ("Lake mohalla, tanker has not come for two days, borewell is dry.", BBMP),

    # -- Layout internal lines, pre-handover ---------------------------------
    ("Green meadows layout, no water in our block since yesterday. Flat 302.", GREEN_MEADOWS),
    ("Green meadows, pump in the layout is not working, no water on third floor.", GREEN_MEADOWS),
    ("Sunrise enclave, water supply to our tower stopped, builder is not responding.", SUNRISE),
    ("Brookefield extension, no water since two days. BWSSB says line is not handed over.", BROOKEFIELD),

    # -- Streets the table does not cover. Correct answer: say so. -----------
    ("9th cross, no water since two days.", None),
    ("Sai layout, water supply stopped completely.", None),
    ("Behind the mosque, 2nd lane, no water for three days.", None),
    ("Anjaneya nagar, taps are dry since Monday.", None),
    ("Ward 7, 1st main, no water supply at all.", None),
    ("New extension road, water not coming.", None),
    ("Opposite the government school, no water since morning.", None),
    ("Cross road near the big temple, water problem since one week.", None),

    # -- Out of scope. The table is water only, so these must not resolve. ---
    ("Garbage has not been collected on 4th cross for a week.", None),
    ("Huge pothole on station road, two-wheelers falling daily.", None),
    ("Street light not working on 7th main since a month.", None),
    ("Sewage overflowing on market road, terrible smell.", None),
    ("Drain is blocked near library road, dirty water on the street.", None),
    ("Streetlight poles on hospital road are all off after 8pm.", None),
]


# ---------------------------------------------------------------------------
# Roads, kept apart from the fifty above so that corpus stays the agreed size and
# its number keeps meaning what it meant. Roads are curated on four demo streets
# only (4th Cross, 1st Stage, 2nd Stage, 8th Main), so a pothole anywhere else
# must still come back unresolved.
#
# The decoy is the one that matters: a hole full of water is still a road
# defect. SERVICE_KEYWORDS checks roads before water, and this pins it, because
# "water" in the complaint is exactly what would send it to BWSSB.
# ---------------------------------------------------------------------------

ROADS_COMPLAINTS: list[tuple[str, str | None]] = [
    ("Huge pothole outside 14, 4th Cross. Bikes are falling every night.", BBMP),
    ("4th cross road has a big pothole near the temple, patched last week and open again.", BBMP),
    ("1st stage, road is broken near the bus stop, deep pothole.", BBMP),
    ("Second stage main stretch full of potholes after the rain.", BBMP),
    ("8th main road dug for cables and left like that, road is broken for two weeks.", BBMP),
    # The decoy: water in the complaint, and still not a BWSSB filing.
    ("Water pooling in the pothole on 4th cross, cannot see how deep it is.", BBMP),
    # No roads entry for these streets. Correct answer: say so.
    ("Pothole on station road near the railway gate.", None),
    ("Kere mohalla, huge pothole in front of the school.", None),
]


def route(text: str, extract: Callable[[str], tuple[Service | None, str]]) -> str | None:
    """Complaint text -> authority, or None when we decline to guess."""
    service, segment = extract(text)
    if service is None or not segment:
        return None
    _tail, entry, citation = resolve(Claim(service=service, segment=segment))
    if entry is None:
        return None
    assert citation, "an entry was returned without a citation -- that is a guess"
    return entry.authority


def evaluate(complaints=COMPLAINTS, extract=keyword_extract) -> dict:
    resolved_hit = resolved_total = declined_hit = declined_total = 0
    failures = []

    for text, expected in complaints:
        got = route(text, extract)
        if expected is None:
            declined_total += 1
            declined_hit += got is None
        else:
            resolved_total += 1
            resolved_hit += got == expected
        if got != expected:
            failures.append((text, expected, got))

    total = resolved_total + declined_total
    return {
        "total": total,
        "correct": resolved_hit + declined_hit,
        # `complaints` is a caller-supplied parameter, so a corpus that is
        # empty or entirely unroutable is reachable. A gate that dies with
        # ZeroDivisionError instead of reporting a number is a gate nobody
        # can read the result of.
        "accuracy": (resolved_hit + declined_hit) / total if total else 0.0,
        "correct_body_rate": resolved_hit / resolved_total if resolved_total else 0.0,
        "declined_correctly": declined_hit,
        "declined_total": declined_total,
        "failures": failures,
    }


def main() -> None:
    r = evaluate()

    print("Routing accuracy -- Ward 12, water")
    print("  overall           " + str(r["correct"]) + "/" + str(r["total"])
          + "  " + format(r["accuracy"], ".0%"))
    print("  correct body      " + format(r["correct_body_rate"], ".0%")
          + "   (of complaints the table should cover)")
    print("  declined to guess " + str(r["declined_correctly"]) + "/"
          + str(r["declined_total"]) + "   (of complaints it should not)")

    if r["failures"]:
        print("\nFailures -- each one is either a missing alias or a missing entry:")
        for text, expected, got in r["failures"]:
            print("  expected " + str(expected) + ", got " + str(got))
            print("    " + text)

    roads = evaluate(ROADS_COMPLAINTS)
    print("\nRouting accuracy -- Ward 12, roads (demo streets)")
    print("  overall           " + str(roads["correct"]) + "/" + str(roads["total"])
          + "  " + format(roads["accuracy"], ".0%"))
    print("  declined to guess " + str(roads["declined_correctly"]) + "/"
          + str(roads["declined_total"]))
    for text, expected, got in roads["failures"]:
        print("  expected " + str(expected) + ", got " + str(got))
        print("    " + text)

    if r["accuracy"] < TARGET or roads["accuracy"] < TARGET:
        print("\nBELOW TARGET (" + format(TARGET, ".0%") + "). Widen the table tonight,"
              " not on Thursday.")
        sys.exit(1)


if __name__ == "__main__":
    main()

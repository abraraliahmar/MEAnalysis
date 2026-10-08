"""Part 3: turn narrator/findings.json into a Situation-Complication-Resolution narrative.

Online path: Gemini via the google-genai client (free AI Studio key in GEMINI_API_KEY).
Offline path: a deterministic template over the same findings, used when no key is set or the call fails.

    python narrator/generate_narrative.py                 # online if a key is set, otherwise offline
    python narrator/generate_narrative.py --offline       # force the keyless path
    python narrator/generate_narrative.py --save-sample   # also save a Gemini run to sample_output.txt
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

NARRATOR_DIR = Path(__file__).resolve().parent
FINDINGS_PATH = NARRATOR_DIR / "findings.json"
SAMPLE_PATH = NARRATOR_DIR / "sample_output.txt"

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MAX_OUTPUT_TOKENS = 1024  # a 3-section, ~250-word narrative needs ~400 tokens; headroom avoids truncation
TIMEOUT_MS = 30_000       # 30 s (google-genai takes milliseconds); the taught minimum is 10 s

SYSTEM_INSTRUCTION = (
    "You are a senior data analyst writing for Mamaearth's regional ops and finance heads. "
    "Write a business narrative of about 250 words using the SCR structure, with exactly three labeled "
    "sections in this order: 'Situation', 'Complication', 'Resolution'. "
    "Every number in your output must come from the findings you are given and appear with the same value; "
    "do not invent, estimate, or derive any other statistic. Write currency as INR with thousands separators "
    "and two decimals, and months by name. Be concrete and plain-spoken, with no filler."
)


def _api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def build_user_prompt(findings: dict) -> str:
    """Interpolate the findings argument, so a different findings.json gives a different prompt."""
    return (
        "Write the SCR narrative from these verified findings (JSON):\n\n"
        f"{json.dumps(findings, indent=2)}\n\n"
        "Cover: what the verified revenue is and how it reconciles to the raw total, what the return-rate "
        "problem is and where it concentrates, and which month is the genuine peak versus the one inflated "
        "by outlier orders. End with concrete recommended actions."
    )


def call_gemini(findings: dict) -> dict:
    """One Gemini call. Always returns a dict; the caller never sees a raw exception."""
    try:
        client = genai.Client(api_key=_api_key())
        response = client.models.generate_content(
            model=MODEL,
            contents=build_user_prompt(findings),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                # temperature 0.0: this is a factual business report, not creative writing, so we want the
                # most deterministic output the model offers and no creative drift away from the findings.
                temperature=0.0,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),  # keep the token budget for the answer
                http_options=types.HttpOptions(timeout=TIMEOUT_MS),
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned no text (possibly blocked or truncated)")
        tokens = response.usage_metadata.total_token_count if response.usage_metadata else None
        return {"status": "success", "narrative": response.text.strip(), "tokens": tokens}
    except Exception as err:  # noqa: BLE001 - deliberately broad: callers get a dict, never an exception
        return {"status": "error", "narrative": None, "message": str(err)}


def _inr(value: float) -> str:
    return f"{value:,.2f}"


def _month_name(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def generate_scr_narrative_offline(findings: dict) -> dict:
    """Deterministic SCR template built straight from findings: no network, no key."""
    pay = findings["return_rate_by_payment"]
    seg = findings["highest_risk_segment"]
    peak = findings["true_peak_month"]
    inflated = findings["outlier_inflated_month"]
    prepaid = {m: r for m, r in pay.items() if m != seg["payment_method"]}
    best_prepaid = min(prepaid, key=prepaid.get)

    narrative = (
        "Situation\n"
        f"After cleaning, verified revenue stands at INR {_inr(findings['cleaned_total_revenue_inr'])}. "
        f"That is INR {_inr(findings['duplicate_reconciliation_delta_inr'])} below the raw total of "
        f"INR {_inr(findings['raw_total_revenue_inr'])}, and the whole gap comes from duplicate orders removed "
        f"during cleaning.\n\n"
        "Complication\n"
        f"{seg['payment_method']} orders are returned at {pay[seg['payment_method']]} percent, against "
        f"{pay[best_prepaid]} percent for {best_prepaid}. The problem is concentrated: "
        f"{seg['payment_method']} orders in Tier-{seg['city_tier']} cities are returned at "
        f"{seg['return_rate_pct']} percent. The headline revenue trend also misleads: "
        f"{_month_name(inflated['month'])} looks strongest at INR {_inr(inflated['apparent_revenue_inr'])}, "
        f"but two bulk orders inflate it, and without them it is INR {_inr(inflated['corrected_revenue_inr'])}.\n\n"
        "Resolution\n"
        f"{_month_name(peak['month'])} is the genuine peak month at INR {_inr(peak['revenue_inr'])}, so plan "
        f"capacity and campaigns around it, not around {_month_name(inflated['month'])}. Target "
        f"{seg['payment_method']} in Tier-{seg['city_tier']} cities first, for example with prepaid incentives "
        f"or order confirmation before dispatch. Review bulk orders separately so they stop distorting "
        f"monthly reporting."
    )
    return {"status": "success", "narrative": narrative, "tokens": None, "source": "offline"}


def generate_scr_narrative(findings: dict) -> dict:
    """Gemini when a key is configured, otherwise (or if the call fails) the offline template."""
    if not _api_key():
        result = generate_scr_narrative_offline(findings)
        result["fallback_reason"] = "no GEMINI_API_KEY / GOOGLE_API_KEY configured"
        return result
    result = call_gemini(findings)
    if result["status"] == "error":
        fallback = generate_scr_narrative_offline(findings)
        fallback["fallback_reason"] = f"Gemini call failed: {result['message']}"
        return fallback
    result["source"] = "gemini"
    return result


def _variants(value: float) -> list:
    """Accepted spellings of a figure, e.g. 97358.3 -> '97358.30' and '97358.3'."""
    return [f"{value:.2f}", f"{value:.2f}".rstrip("0").rstrip(".")]


def check_figures(narrative: str, findings: dict) -> bool:
    """Assert the five required figures are present (commas ignored); print a pass/fail line for each."""
    text = narrative.replace(",", "")
    peak = findings["true_peak_month"]
    checks = [
        ("cleaned total revenue", _variants(findings["cleaned_total_revenue_inr"])),
        ("COD return rate", [str(findings["return_rate_by_payment"]["COD"])]),
        ("highest-risk segment rate", [str(findings["highest_risk_segment"]["return_rate_pct"])]),
        ("reconciliation delta", _variants(findings["duplicate_reconciliation_delta_inr"])),
        ("peak month name", [_month_name(peak["month"]).split()[0]]),
        ("peak month revenue", _variants(peak["revenue_inr"])),
    ]
    all_ok = True
    for label, options in checks:
        ok = any(o in text for o in options)
        all_ok &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {' or '.join(options)}")
    return all_ok


def main(argv):
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    if "--offline" in argv:
        result = generate_scr_narrative_offline(findings)
    else:
        result = generate_scr_narrative(findings)

    print(f"Source: {result['source']}" + (f"  ({result['fallback_reason']})" if "fallback_reason" in result else ""))
    if result["tokens"] is not None:
        print(f"Tokens used: {result['tokens']}")
    print(f"\n{result['narrative']}\n\nNumeric accuracy check:")
    ok = check_figures(result["narrative"], findings)
    print("ALL FIGURES PRESENT" if ok else "MISSING FIGURES")

    if "--save-sample" in argv:
        if result["source"] != "gemini":
            print("Not saving sample_output.txt: this run did not come from Gemini.")
        else:
            SAMPLE_PATH.write_text(result["narrative"] + "\n", encoding="utf-8")
            print(f"Saved {SAMPLE_PATH.name}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

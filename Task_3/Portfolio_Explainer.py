"""
Timecell AI — Task 03: AI-Powered Portfolio Explainer
Author: [Your Name]

Uses Groq (llama-3.1-8b-instant) to generate plain-English portfolio risk
explanations in the voice of a senior wealth advisor named Arjun.

Why Groq / llama-3.1-8b-instant:
  - Completely free tier: 14,400 requests/day, no credit card required
  - OpenAI-compatible API — minimal code changes from original GPT design
  - Fast responses (~1s), strong instruction-following for structured XML output
  - llama-3.1-8b-instant follows system/user split + XML format reliably

Architecture — clean separation of concerns:
    1. build_portfolio_context()   → computes ALL metrics, formats for LLM
    2. build_system_prompt()       → role + rules (tone-aware persona)
    3. build_user_prompt()         → task + exact XML output format
    4. call_llm()                  → single Groq API call, raw text back
    5. parse_response()            → extracts structured fields from XML tags
    6. critique_explanation()      → BONUS: 2nd LLM call audits the first
    7. print_report()              → renders structured + raw output

Run:
    python Portfolio_Explainer.py
    python Portfolio_Explainer.py --tone beginner
    python Portfolio_Explainer.py --tone expert
    python Portfolio_Explainer.py --portfolio aggressive
    python Portfolio_Explainer.py --portfolio conservative
    python Portfolio_Explainer.py --critique
    python Portfolio_Explainer.py --demo        # no API key needed
    python Portfolio_Explainer.py --no-raw      # hide raw API response
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from groq import Groq

# Load .env automatically (GROQ_API_KEY lives there)
load_dotenv()

# ─────────────────────────────────────────────────────────────
# Types & constants
# ─────────────────────────────────────────────────────────────

Tone    = Literal["beginner", "experienced", "expert"]
Verdict = Literal["Aggressive", "Balanced", "Conservative"]
MODEL   = "llama-3.1-8b-instant"


# ─────────────────────────────────────────────────────────────
# Sample portfolios
# ─────────────────────────────────────────────────────────────

PORTFOLIOS = {
    "sample": {
        "total_value_inr": 10_000_000,
        "monthly_expenses_inr": 80_000,
        "assets": [
            {"name": "BTC",     "allocation_pct": 30, "expected_crash_pct": -80},
            {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
            {"name": "GOLD",    "allocation_pct": 20, "expected_crash_pct": -15},
            {"name": "CASH",    "allocation_pct": 10, "expected_crash_pct":   0},
        ],
    },
    "conservative": {
        "total_value_inr": 5_000_000,
        "monthly_expenses_inr": 50_000,
        "assets": [
            {"name": "GOLD",       "allocation_pct": 35, "expected_crash_pct": -15},
            {"name": "GOVT_BONDS", "allocation_pct": 40, "expected_crash_pct":  -5},
            {"name": "CASH",       "allocation_pct": 25, "expected_crash_pct":   0},
        ],
    },
    "aggressive": {
        "total_value_inr": 2_000_000,
        "monthly_expenses_inr": 30_000,
        "assets": [
            {"name": "BTC",     "allocation_pct": 50, "expected_crash_pct": -80},
            {"name": "ETH",     "allocation_pct": 30, "expected_crash_pct": -75},
            {"name": "NIFTY50", "allocation_pct": 20, "expected_crash_pct": -40},
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# Step 1 — Build portfolio context
#
# ALL arithmetic is done here — not by the LLM.
# LLMs are unreliable at arithmetic. We hand Llama the finished
# numbers and tell it to trust them. This is the single biggest
# factor preventing hallucinated calculations.
# ─────────────────────────────────────────────────────────────

def build_portfolio_context(portfolio: dict) -> str:
    total    = portfolio["total_value_inr"]
    expenses = portfolio["monthly_expenses_inr"]
    assets   = portfolio["assets"]

    # Post-crash portfolio value
    post_crash = sum(
        (total * a["allocation_pct"] / 100) * (1 + a["expected_crash_pct"] / 100)
        for a in assets
    )
    runway = post_crash / expenses if expenses > 0 else float("inf")
    ruin   = "PASS" if runway > 12 else "FAIL"

    # Risk score = allocation × crash magnitude (higher = riskier)
    for a in assets:
        a["_risk_score"] = a["allocation_pct"] * abs(a["expected_crash_pct"])

    biggest_risk       = max(assets, key=lambda a: a["_risk_score"])
    concentration_flag = any(a["allocation_pct"] > 40 for a in assets)

    # Crash loss in absolute terms (helpful for the LLM to reference)
    crash_loss = total - post_crash

    lines = [
        "── PORTFOLIO SNAPSHOT ───────────────────────────",
        f"  Total value       : ₹{total:,.0f}",
        f"  Monthly expenses  : ₹{expenses:,.0f}",
        "",
        "  Asset breakdown (sorted by allocation):",
    ]
    for a in sorted(assets, key=lambda x: x["allocation_pct"], reverse=True):
        val = total * a["allocation_pct"] / 100
        lines.append(
            f"    {a['name']:<14} {a['allocation_pct']:>3}%   "
            f"₹{val:>12,.0f}   worst-case crash: {a['expected_crash_pct']:>4}%"
        )
    lines += [
        "",
        "── PRE-COMPUTED RISK METRICS ─────────────────────",
        f"  Post-crash value  : ₹{post_crash:,.0f}",
        f"  Crash loss        : ₹{crash_loss:,.0f}",
        f"  Expense runway    : {runway:.1f} months  ({runway/12:.1f} years)",
        f"  Ruin test (>12mo) : {ruin}",
        f"  Biggest risk asset: {biggest_risk['name']} "
        f"(risk score {biggest_risk['_risk_score']:.0f})",
        f"  Concentration flag: {'YES — one asset >40%' if concentration_flag else 'NO'}",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Step 2 — Prompt engineering
#
# What we tried and why we landed here:
#
#  Attempt 1 — flat single prompt:
#    "Explain this portfolio risk in plain English."
#    Problem: inconsistent length, no parseable structure,
#    sometimes bullet lists instead of paragraphs.
#
#  Attempt 2 — JSON output:
#    Llama wraps in ```json fences, quotes inside values
#    break parsing, inconsistent key names. Very fragile.
#
#  Attempt 3 (final) — system/user split + XML tags:
#    System = persona + rules + tone. Stable, not per-request.
#    User   = data + exact XML format with field instructions.
#    XML survives fences, escaping issues, and whitespace.
#    Llama follows it reliably with temperature=0.4.
#
#  Key rules that made the biggest difference:
#    - "Trust the numbers" → stops Llama re-doing arithmetic
#    - "Every claim must trace to a number" → no vague advice
#    - "No filler openers" → kills "Great portfolio!" responses
#    - "Output ONLY the four XML tags" → no preamble/postamble
#    - temperature=0.4 → consistent structure, fewer hallucinations
# ─────────────────────────────────────────────────────────────

TONE_PERSONAS: dict[str, str] = {
    "beginner": (
        "Your client is completely new to investing and finds financial "
        "jargon intimidating. Use everyday analogies — compare the portfolio "
        "to familiar things like a safety net or a rainy-day fund. Never use "
        "terms like 'volatility', 'drawdown', or 'correlation' without "
        "immediately explaining them in one simple sentence. Your tone is warm, "
        "like a trusted older sibling who happens to know about money — honest "
        "about risks, but never scary or condescending."
    ),
    "experienced": (
        "Your client understands basic investing: they know what diversification, "
        "asset classes, and risk-return tradeoffs mean. You can use standard "
        "financial terms without defining them. Skip the basics. Be direct, "
        "practical, and concrete — they want specific numbers and specific "
        "actions, not generalities."
    ),
    "expert": (
        "Your client is a sophisticated investor or finance professional. Use "
        "precise language: concentration risk, tail risk, drawdown, correlation, "
        "rebalancing triggers. Be terse and analytical. Surface non-obvious "
        "insights they might not have considered. Do not explain things they "
        "already know."
    ),
}


def build_system_prompt(tone: Tone) -> str:
    """
    System prompt = role + non-negotiable rules + tone persona.
    Sent as the 'system' role so the LLM treats it as persistent
    context, not part of the conversation.
    """
    return f"""You are Arjun, a senior wealth advisor at Timecell — an AI-powered \
wealth management platform built for high-net-worth Indian families. You have \
18 years of experience across equity markets, crypto, and alternative assets. \
Clients trust you because you give them the real picture, not what they want to hear.

AUDIENCE & TONE
{TONE_PERSONAS[tone]}

NON-NEGOTIABLE RULES
1. All numbers in the portfolio context are pre-verified. Trust them — do not recalculate.
2. Every claim you make must trace back to a specific number in the data provided.
3. Never open with filler like "Great portfolio!", "As an AI...", or "Thank you for sharing".
4. Never close with "please consult a financial advisor" or any generic disclaimer.
5. Your output must contain ONLY the four XML tags specified. Nothing before or after them.
6. Use ₹ symbol and Lakh/Crore notation where natural (e.g. ₹57 lakhs, not ₹5,700,000).
7. Close every XML tag properly: </summary>, </doing_well>, </consider_changing>, </verdict>."""


def build_user_prompt(portfolio_context: str) -> str:
    """
    User prompt = the actual portfolio data + exact output spec.
    Field-level instructions keep each section tightly focused.
    """
    return f"""Here is a client's portfolio for your review:

{portfolio_context}

Write your assessment in EXACTLY this XML format. Nothing outside these four tags.

<summary>
3 to 4 sentences. Tell the client what their numbers actually mean for their life — \
not a restatement of the data, but the real-world implication. If their runway is \
71 months, what does that feel like? If one asset could halve their wealth, say so plainly. \
End with the single most important thing to understand about this portfolio right now.
</summary>

<doing_well>
1 to 2 sentences. One specific, genuine strength grounded in actual numbers. \
Name the asset or metric. Say what it protects them from. No generic praise.
</doing_well>

<consider_changing>
2 to 3 sentences. One concrete, actionable recommendation. Name the specific asset, \
the specific action (e.g. "reduce BTC from 30% to 15%"), the specific amount freed up, \
and exactly which risk that addresses. Do not say "diversify more" — say what to buy or sell.
</consider_changing>

<verdict>
Exactly one word: Aggressive or Balanced or Conservative. \
Base this strictly on crash survival runway and risk score distribution. \
Portfolios dominated by crypto or high-crash assets are Aggressive. \
Portfolios with bonds, gold, and cash are Conservative. \
Mixed portfolios with reasonable runway are Balanced.
</verdict>"""


# ─────────────────────────────────────────────────────────────
# Step 3 — Groq API call
#
# Why Groq: completely free (14,400 req/day), no credit card,
# OpenAI-compatible API means the code structure is identical
# to the original GPT-4o-mini design.
# ─────────────────────────────────────────────────────────────

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Single Groq API call.
    system_prompt → system role message (persistent instructions)
    user_prompt   → user role message (the actual request + data)
    Returns raw text. Raises on auth/connection errors.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not found.\n"
            "Add it to your .env file:\n\n"
            "    GROQ_API_KEY=gsk_...\n\n"
            "Get a free key at: https://console.groq.com"
        )

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,       # low = consistent structure, fewer hallucinations
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


# ─────────────────────────────────────────────────────────────
# Step 4 — Parse structured output
#
# XML extraction is deliberately simple — no external libraries.
# The fence-stripping step handles cases where Llama wraps
# its output in ```xml ... ``` markdown blocks despite instructions.
# ─────────────────────────────────────────────────────────────

@dataclass
class ExplainerOutput:
    summary:           str
    doing_well:        str
    consider_changing: str
    verdict:           str
    raw_response:      str
    tone:              Tone
    used_fallback:     bool = False


def _strip_fences(text: str) -> str:
    """Remove markdown code fences Llama sometimes adds despite instructions."""
    return re.sub(r"```[a-z]*\n?", "", text).strip()


def _extract_tag(text: str, tag: str) -> str:
    """Extract content between <tag>…</tag>. Returns '' if tag missing."""
    start = text.find(f"<{tag}>")
    end   = text.find(f"</{tag}>")
    if start == -1 or end == -1:
        return ""
    return text[start + len(f"<{tag}>"):end].strip()


VALID_VERDICTS = {"Aggressive", "Balanced", "Conservative"}


def parse_response(raw: str, tone: Tone, used_fallback: bool = False) -> ExplainerOutput:
    cleaned = _strip_fences(raw)

    summary           = _extract_tag(cleaned, "summary")
    doing_well        = _extract_tag(cleaned, "doing_well")
    consider_changing = _extract_tag(cleaned, "consider_changing")
    verdict_raw       = _extract_tag(cleaned, "verdict")

    # Normalise — handles "Aggressive." / "**Balanced**" / extra whitespace
    verdict = verdict_raw.strip(" .*_\n").capitalize()
    if verdict not in VALID_VERDICTS:
        for v in VALID_VERDICTS:
            if v.lower() in verdict_raw.lower():
                verdict = v
                break
        else:
            verdict = "Balanced"

    return ExplainerOutput(
        summary           = summary           or "⚠ parse error — <summary> tag missing",
        doing_well        = doing_well        or "⚠ parse error — <doing_well> tag missing",
        consider_changing = consider_changing or "⚠ parse error — <consider_changing> tag missing",
        verdict           = verdict,
        raw_response      = raw,
        tone              = tone,
        used_fallback     = used_fallback,
    )


# ─────────────────────────────────────────────────────────────
# Step 5 (BONUS) — Critique call
# Second Groq call with a completely different persona.
# Same call_llm() function — demonstrates reusability.
# ─────────────────────────────────────────────────────────────

def critique_explanation(output: ExplainerOutput, portfolio_context: str) -> str:
    """
    Second LLM call: a risk analyst audits the first explanation.
    Different system persona = independent perspective.
    """
    critique_system = (
        "You are a senior risk analyst at a financial regulator auditing "
        "AI-generated financial advice. You are not the author — you are "
        "reviewing someone else's work. Be specific and critical. Reference "
        "exact numbers from the portfolio data. If something is wrong or "
        "missing, say so directly. "
        "Output ONLY the three XML tags specified. Nothing else. "
        "Close every XML tag properly."
    )
    critique_user = f"""Audit this AI-generated portfolio explanation.

=== PORTFOLIO DATA ===
{portfolio_context}

=== EXPLANATION UNDER REVIEW ===
SUMMARY          : {output.summary}
DOING WELL       : {output.doing_well}
CONSIDER CHANGING: {output.consider_changing}
VERDICT          : {output.verdict}

<accuracy>
Are any statements factually wrong or misleading given the numbers?
If everything checks out, confirm it and say why.
</accuracy>

<omissions>
What important risks or context did the advisor miss?
Reference specific numbers from the portfolio data.
</omissions>

<verdict_check>
Is "{output.verdict}" the correct classification? Justify in 1-2 sentences.
</verdict_check>"""

    return call_llm(critique_system, critique_user)


# ─────────────────────────────────────────────────────────────
# Demo mode — works with no API key, for testing/presentation
# ─────────────────────────────────────────────────────────────

DEMO_RAW = """<summary>
Your portfolio sits in genuinely risky territory. In a severe market crash — the kind
that has happened multiple times in the last 15 years — it could lose close to ₹43
lakhs, dropping from ₹1 crore to around ₹57 lakhs. The silver lining is real: even
at that reduced value, you have over 71 months of living expenses covered, which means
you would not be forced to sell anything at the worst possible time. But that cushion
exists only because you have NIFTY50, gold, and cash alongside BTC — and right now,
Bitcoin is the single variable most likely to determine whether this portfolio grows
or gets cut in half.
</summary>

<doing_well>
Your combined gold and cash allocation of 30% — roughly ₹30 lakhs sitting in assets
that either hold their value or drop minimally in a crash — gives you a genuine
safety net. It means you have nearly 3 years of expenses protected even before
touching your equity positions.
</doing_well>

<consider_changing>
Your BTC position carries a risk score of 2,400 — more than twice that of your
NIFTY50 allocation. Consider trimming BTC from 30% to 15% and redirecting the
freed ₹15 lakhs into a NIFTY50 index fund: this single change cuts your worst-case
crash loss by roughly ₹12 lakhs while keeping meaningful crypto upside if Bitcoin
continues its long-term trend.
</consider_changing>

<verdict>
Aggressive
</verdict>"""

DEMO_CRITIQUE = """<accuracy>
The explanation is factually grounded. The ₹57 lakh post-crash figure and 71-month
runway both check out against the pre-computed metrics. The BTC risk score of 2,400
(30 × 80) is correct and more specific than most AI-generated advice.
</accuracy>

<omissions>
The explanation does not flag that BTC and NIFTY50 tend to correlate positively
during broad market sell-offs — meaning both could fall simultaneously, compressing
the actual runway below the 71-month figure. The 10% cash position earning
near-zero real returns in an inflationary environment also goes unmentioned.
</omissions>

<verdict_check>
Aggressive is correct. A 30% BTC allocation with a worst-case -80% crash and
a weighted portfolio loss of 43% places this firmly in aggressive territory
by any standard classification framework.
</verdict_check>"""


# ─────────────────────────────────────────────────────────────
# Renderer — ANSI colour output
# ─────────────────────────────────────────────────────────────

ANSI = {
    "green":  "\033[92m",
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "cyan":   "\033[96m",
    "blue":   "\033[94m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "reset":  "\033[0m",
}

def _c(text: str, *styles: str) -> str:
    return "".join(ANSI[s] for s in styles) + text + ANSI["reset"]

VERDICT_COLOUR = {"Aggressive": "red", "Balanced": "yellow", "Conservative": "green"}

def _wrap(text: str, width: int = 68, indent: str = "  ") -> str:
    """Word-wrap text to width, preserving paragraph breaks."""
    paragraphs = text.split("\n\n")
    wrapped = []
    for para in paragraphs:
        words = para.split()
        lines, line = [], []
        for word in words:
            if sum(len(w) + 1 for w in line) + len(word) > width:
                lines.append(indent + " ".join(line))
                line = [word]
            else:
                line.append(word)
        if line:
            lines.append(indent + " ".join(line))
        wrapped.append("\n".join(lines))
    return "\n\n".join(wrapped)


def print_report(output: ExplainerOutput, show_raw: bool = True) -> None:
    if output.used_fallback:
        print(_c("\n  ⚡ DEMO MODE — mock response, no API call made", "yellow"))

    print()
    print(_c("  ╔════════════════════════════════════════════════════╗", "cyan"))
    print(_c("  ║     TIMECELL  ·  PORTFOLIO RISK EXPLAINER          ║", "cyan", "bold"))
    print(_c("  ╚════════════════════════════════════════════════════╝", "cyan"))
    print(_c(f"  Tone: {output.tone.upper()}   Model: {MODEL}", "dim"))
    print()

    vc = VERDICT_COLOUR.get(output.verdict, "yellow")
    print(_c(f"  ┌─────────────────────────────────┐", vc))
    print(_c(f"  │   VERDICT :  {output.verdict:<19}│", vc, "bold"))
    print(_c(f"  └─────────────────────────────────┘", vc))
    print()

    for title, content in [
        ("📊  RISK SUMMARY",      output.summary),
        ("✅  DOING WELL",        output.doing_well),
        ("⚠   CONSIDER CHANGING", output.consider_changing),
    ]:
        print(_c(f"  {title}", "bold"))
        print(_c("  " + "─" * 52, "dim"))
        print(_wrap(content))
        print()

    if show_raw:
        print(_c("  ── RAW API RESPONSE " + "─" * 33, "dim"))
        for line in output.raw_response.splitlines():
            print(_c("  " + line, "dim"))
        print()


def print_critique(raw: str) -> None:
    print()
    print(_c("  ╔════════════════════════════════════════════════════╗", "blue"))
    print(_c("  ║     SELF-CRITIQUE  ·  2nd LLM call                 ║", "blue", "bold"))
    print(_c("  ╚════════════════════════════════════════════════════╝", "blue"))
    print()
    cleaned = _strip_fences(raw)
    for tag, title in [
        ("accuracy",      "🔍  ACCURACY CHECK"),
        ("omissions",     "📋  OMISSIONS"),
        ("verdict_check", "⚖   VERDICT CHECK"),
    ]:
        content = _extract_tag(cleaned, tag)
        if not content:
            continue
        print(_c(f"  {title}", "bold"))
        print(_c("  " + "─" * 52, "dim"))
        print(_wrap(content))
        print()


# ─────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────

def explain_portfolio(
    portfolio: dict,
    tone: Tone = "experienced",
    run_critique: bool = False,
    demo: bool = False,
) -> ExplainerOutput:

    context     = build_portfolio_context(portfolio)
    sys_prompt  = build_system_prompt(tone)
    user_prompt = build_user_prompt(context)

    print(_c("\n  [1/3]  Portfolio metrics computed.", "dim"))
    print(_c(f"  [2/3]  Calling {MODEL} via Groq...", "dim"))

    if demo:
        raw = DEMO_RAW
        print(_c("         (demo mode — mock response used)", "yellow"))
    else:
        raw = call_llm(sys_prompt, user_prompt)

    print(_c("  [3/3]  Parsing structured output.", "dim"))
    output = parse_response(raw, tone, used_fallback=demo)

    if run_critique:
        print(_c("  [+]    Running critique (2nd LLM call)...", "dim"))
        critique_raw = DEMO_CRITIQUE if demo else critique_explanation(output, context)
        print_critique(critique_raw)

    return output


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Timecell — AI Portfolio Explainer (Groq / llama-3.1-8b-instant)"
    )
    parser.add_argument(
        "--tone", choices=["beginner", "experienced", "expert"],
        default="experienced",
        help="Audience tone for the explanation (default: experienced)",
    )
    parser.add_argument(
        "--portfolio", choices=list(PORTFOLIOS.keys()),
        default="sample",
        help="Which portfolio to analyse (default: sample)",
    )
    parser.add_argument(
        "--critique", action="store_true",
        help="Run a second LLM call to critique the first explanation",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Use a mock response — no API key required",
    )
    parser.add_argument(
        "--no-raw", action="store_true",
        help="Hide the raw API response section",
    )
    args = parser.parse_args()

    try:
        output = explain_portfolio(
            portfolio    = PORTFOLIOS[args.portfolio],
            tone         = args.tone,
            run_critique = args.critique,
            demo         = args.demo,
        )
        print_report(output, show_raw=not args.no_raw)

    except EnvironmentError as e:
        print(_c(f"\n  ❌  {e}", "red"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(_c(f"\n  ❌  Error: {type(e).__name__}: {e}", "red"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
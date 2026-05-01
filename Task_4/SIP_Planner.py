
import math
import os
import datetime

# ── ANSI COLOURS ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
MAGENTA= "\033[95m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")

def fmt_inr(amount: float) -> str:
    """Format a number as Indian Rupee string with crore/lakh suffix."""
    amount = round(amount)
    if amount >= 1_00_00_000:
        return f"₹{amount/1_00_00_000:.2f} Cr"
    elif amount >= 1_00_000:
        return f"₹{amount/1_00_000:.2f} L"
    else:
        return f"₹{amount:,.0f}"

def fmt_bar(value: float, max_value: float, width: int = 28) -> str:
    """Return a filled progress bar string."""
    filled = int((value / max_value) * width) if max_value > 0 else 0
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    return bar

def parse_inr_input(raw: str) -> float:
    """
    Accept inputs like:
      50L / 50l / 50 lakh / 50,00,000 / 5000000 / 1.5Cr / 1.5cr
    Returns float in rupees.
    """
    raw = raw.strip().replace(",", "").lower()
    if raw.endswith("cr"):
        return float(raw[:-2]) * 1_00_00_000
    elif "crore" in raw:
        return float(raw.replace("crore", "").strip()) * 1_00_00_000
    elif raw.endswith("l"):
        return float(raw[:-1]) * 1_00_000
    elif "lakh" in raw:
        return float(raw.replace("lakh", "").strip()) * 1_00_000
    else:
        return float(raw)

def ask(prompt: str, default=None):
    """Prompt user; show default in brackets."""
    if default is not None:
        display = f"{CYAN}{prompt}{RESET} [{DIM}{default}{RESET}]: "
    else:
        display = f"{CYAN}{prompt}{RESET}: "
    val = input(display).strip()
    return val if val else str(default)

# ── CORE FINANCE MATH ─────────────────────────────────────────────────────────

def compute_sip(goal: float, current_savings: float, annual_return_pct: float,
                years: int) -> dict:
    """
    Given a goal, existing corpus, expected return, and horizon:
    → future value of current savings (lump sum compounded)
    → shortfall that SIP must cover
    → required monthly SIP using standard FV-of-annuity formula
    → year-by-year breakdown
    """
    r_monthly = annual_return_pct / 100 / 12
    n_months  = years * 12

    # Future value of existing lump-sum corpus
    fv_lumpsum = current_savings * ((1 + r_monthly) ** n_months)

    # Shortfall SIP needs to cover
    shortfall = max(goal - fv_lumpsum, 0)

    # Required SIP: FV = SIP × [((1+r)^n - 1) / r] × (1+r)
    if shortfall == 0:
        sip_required = 0.0
    else:
        if r_monthly == 0:
            sip_required = shortfall / n_months
        else:
            factor = (((1 + r_monthly) ** n_months) - 1) / r_monthly * (1 + r_monthly)
            sip_required = shortfall / factor

    # Year-by-year breakdown
    yearly = []
    corpus = current_savings
    total_invested = current_savings  # lump-sum counts as invested

    for yr in range(1, years + 1):
        for _ in range(12):
            corpus = corpus * (1 + r_monthly) + sip_required
        total_invested += sip_required * 12
        gains = corpus - total_invested
        yearly.append({
            "year":           yr,
            "corpus":         corpus,
            "total_invested": total_invested,
            "total_gains":    gains,
            "progress_pct":   min(corpus / goal * 100, 100),
        })

    return {
        "goal":           goal,
        "current_savings":current_savings,
        "annual_return":  annual_return_pct,
        "years":          years,
        "fv_lumpsum":     fv_lumpsum,
        "shortfall":      shortfall,
        "sip_required":   sip_required,
        "total_sip_paid": sip_required * n_months,
        "final_corpus":   yearly[-1]["corpus"] if yearly else current_savings,
        "total_invested": yearly[-1]["total_invested"] if yearly else current_savings,
        "total_gains":    yearly[-1]["total_gains"] if yearly else 0,
        "yearly":         yearly,
    }

def goal_presets() -> dict | None:
    """Show common goal presets and return chosen values or None to skip."""
    presets = [
        ("Child's Higher Education",  "50L",  "12", "12"),
        ("Child's Wedding",           "1Cr",  "15", "11"),
        ("Retirement Corpus",         "5Cr",  "20", "10"),
        ("Property Down Payment",     "30L",  "5",  "10"),
        ("Overseas Vacation Fund",    "10L",  "3",  "9"),
    ]
    print(f"\n  {BOLD}Common Goals (press 1-5 to auto-fill, or 0 to enter manually):{RESET}")
    for i, (name, goal, yrs, ret) in enumerate(presets, 1):
        print(f"    {DIM}{i}.{RESET} {name:<30} Goal: {YELLOW}{goal:<8}{RESET}  "
              f"{yrs} yrs  @{ret}% p.a.")
    print()
    choice = input(f"  {CYAN}Choose preset or 0 for manual{RESET}: ").strip()
    if choice in [str(i) for i in range(1, len(presets)+1)]:
        idx = int(choice) - 1
        name, goal, yrs, ret = presets[idx]
        print(f"\n  {GREEN}✓ Loaded: {name}{RESET}")
        return {"goal": goal, "years": yrs, "return": ret}
    return None

# ── DISPLAY ───────────────────────────────────────────────────────────────────

def print_header():
    print()
    print(f"  {'━'*64}")
    print(f"  {BOLD}{CYAN}  💰  TIMECELL.AI — SIP GOAL PLANNER{RESET}")
    print(f"  {DIM}  AI-powered wealth planning for HNI Indian families{RESET}")
    print(f"  {'━'*64}")

def print_summary(res: dict, goal_label: str):
    w = 64
    def row(label, value, colour=RESET):
        print(f"  │  {label:<28}{colour}{BOLD}{value:>28}{RESET}  │")
    def divider():
        print(f"  ├{'─'*w}┤")
    def blank():
        print(f"  │{'':^{w}}│")

    print()
    print(f"  ┌{'─'*w}┐")
    title = f"📋  PLAN SUMMARY — {goal_label.upper()}"
    print(f"  │  {BOLD}{title:<{w-2}}{RESET}  │")
    divider()
    blank()
    row("Goal Amount",        fmt_inr(res['goal']),             YELLOW)
    row("Time Horizon",       f"{res['years']} years",          CYAN)
    row("Expected Return",    f"{res['annual_return']}% p.a.",  CYAN)
    row("Existing Savings",   fmt_inr(res['current_savings']),  GREEN)
    blank()
    divider()
    blank()

    if res['sip_required'] == 0:
        row("Required Monthly SIP", "₹0  (already on track!)", GREEN)
    else:
        row("Required Monthly SIP",  fmt_inr(res['sip_required']),   GREEN)
        row("  → Annual SIP",        fmt_inr(res['sip_required']*12),DIM)

    blank()
    divider()
    blank()
    row("Total Amount Invested",  fmt_inr(res['total_invested']),  CYAN)
    row("Total Wealth Gained",    fmt_inr(res['total_gains']),     GREEN)
    row("Final Corpus",           fmt_inr(res['final_corpus']),    YELLOW)

    gain_ratio = res['total_gains'] / max(res['total_invested'], 1) * 100
    row("Return on Investment",   f"{gain_ratio:.1f}%",            MAGENTA)
    blank()
    print(f"  └{'─'*w}┘")

def print_yearly_table(res: dict):
    print()
    print(f"  {BOLD}{CYAN}📅  YEAR-BY-YEAR GROWTH{RESET}")
    print()
    header = (f"  {'Year':>4}  {'Corpus':>14}  {'Invested':>14}  "
              f"{'Gains':>12}  {'Progress':>8}  {'':28}")
    print(f"  {DIM}{header.strip()}{RESET}")
    print(f"  {'─'*100}")

    max_corpus = res['yearly'][-1]['corpus']

    for row in res['yearly']:
        yr       = row['year']
        corpus   = row['corpus']
        invested = row['total_invested']
        gains    = row['total_gains']
        pct      = row['progress_pct']
        bar      = fmt_bar(corpus, max_corpus, width=24)

        # colour shifts as goal approaches
        if pct >= 90:
            col = GREEN
        elif pct >= 50:
            col = YELLOW
        else:
            col = CYAN

        # milestone flags
        flag = ""
        if pct >= 100 and not flag:
            flag = f" {GREEN}🎯 GOAL!{RESET}"
        elif yr % 5 == 0:
            flag = f" {DIM}↑ {yr}yr mark{RESET}"

        print(f"  {BOLD}{yr:>4}{RESET}  "
              f"{col}{fmt_inr(corpus):>14}{RESET}  "
              f"{DIM}{fmt_inr(invested):>14}{RESET}  "
              f"{GREEN}{fmt_inr(gains):>12}{RESET}  "
              f"{pct:>7.1f}%  "
              f"{col}{bar}{RESET}"
              f"{flag}")

    print(f"  {'─'*100}")

def print_insights(res: dict):
    sip     = res['sip_required']
    goal    = res['goal']
    savings = res['current_savings']

    print()
    print(f"  {BOLD}{YELLOW}💡  ADVISOR INSIGHTS{RESET}")
    print()

    # Insight 1 — lump sum impact
    if savings > 0:
        lump_pct = res['fv_lumpsum'] / goal * 100
        print(f"  {GREEN}▸{RESET} Your existing ₹{savings/1e5:.1f}L corpus will grow to "
              f"{fmt_inr(res['fv_lumpsum'])} — covering "
              f"{BOLD}{lump_pct:.1f}%{RESET} of your goal on its own.")

    # Insight 2 — wealth multiplier
    multiplier = res['final_corpus'] / max(res['total_invested'], 1)
    print(f"  {GREEN}▸{RESET} Every rupee you invest will grow to "
          f"{BOLD}{YELLOW}₹{multiplier:.2f}{RESET} by the end — "
          f"the power of compounding.")

    # Insight 3 — SIP affordability nudge
    if sip > 0:
        daily = sip / 30
        print(f"  {GREEN}▸{RESET} {fmt_inr(sip)}/month = just "
              f"{BOLD}{fmt_inr(daily)}/day{RESET}. Small daily discipline, big outcome.")

    # Insight 4 — step-up suggestion
    if sip > 0:
        stepup_sip = sip * 0.85
        print(f"  {GREEN}▸{RESET} If you increase SIP by 10% each year, "
              f"you could start with just {BOLD}{YELLOW}{fmt_inr(stepup_sip)}/month{RESET} "
              f"and still hit the goal.")

    print()

# ── MAIN FLOW ─────────────────────────────────────────────────────────────────

def main():
    clear()
    print_header()

    # ── preset or manual ──
    preset = goal_presets()

    print()
    print(f"  {BOLD}Enter your goal details:{RESET}  "
          f"{DIM}(use formats like 50L, 1Cr, 5000000){RESET}\n")

    # Goal label
    goal_label = ask("  Goal name (e.g. Child's Education)", "My Financial Goal")

    # Goal amount
    default_goal = preset["goal"] if preset else "50L"
    while True:
        try:
            goal = parse_inr_input(ask("  Target amount", default_goal))
            if goal <= 0: raise ValueError
            break
        except ValueError:
            print(f"  {RED}Invalid amount. Try: 50L / 1Cr / 5000000{RESET}")

    # Current savings
    while True:
        try:
            savings = parse_inr_input(ask("  Existing savings / lump sum today", "0"))
            if savings < 0: raise ValueError
            break
        except ValueError:
            print(f"  {RED}Must be 0 or more.{RESET}")

    # Time horizon
    default_yrs = preset["years"] if preset else "10"
    while True:
        try:
            years = int(ask("  Time horizon (years)", default_yrs))
            if years <= 0: raise ValueError
            break
        except ValueError:
            print(f"  {RED}Must be a positive integer.{RESET}")

    # Expected return
    default_ret = preset["return"] if preset else "12"
    while True:
        try:
            ret = float(ask("  Expected annual return (%)", default_ret))
            if ret < 0: raise ValueError
            break
        except ValueError:
            print(f"  {RED}Must be 0 or more.{RESET}")

    # ── compute ──
    res = compute_sip(goal, savings, ret, years)

    # ── display ──
    clear()
    print_header()
    print_summary(res, goal_label)
    print_yearly_table(res)
    print_insights(res)

    # ── export option ──
    export = input(f"  {CYAN}Export results to CSV? (y/n){RESET} [n]: ").strip().lower()
    if export == "y":
        fname = f"sip_plan_{goal_label.replace(' ','_').lower()}.csv"
        with open(fname, "w") as f:
            f.write("Year,Corpus_INR,Total_Invested_INR,Total_Gains_INR,Progress_Pct\n")
            for row in res["yearly"]:
                f.write(f"{row['year']},{row['corpus']:.0f},"
                        f"{row['total_invested']:.0f},{row['total_gains']:.0f},"
                        f"{row['progress_pct']:.2f}\n")
        print(f"  {GREEN}✓ Saved to {fname}{RESET}")

    print()
    print(f"  {DIM}Generated by Timecell.ai SIP Planner · "
          f"{datetime.date.today().strftime('%d %b %Y')}{RESET}")
    print()

if __name__ == "__main__":
    main()
# Timecell Intern Technical Assessment 

This is my submission for the Timecell.ai Summer Internship technical test. I used Claude as my primary AI coding assistant throughout all four tasks. Below I have documented my approach for each task, what I built, where I got stuck, and how I actually worked with Claude to get there.

---

## How I Used Claude

I did not use Claude to dump a single prompt and copy-paste the output. My approach was to break each task into logical pieces, prompt Claude for each piece separately, understand what it gave me, and then ask it to merge everything into a final clean script. For example for Task 01 I first asked Claude to model the data structures, then separately asked for the crash math, then the display layer, and finally one prompt to tie it all together coherently. This way I could actually understand and explain every part.

I will mention my specific prompts and decisions under each task.

---

## Task 01 — Portfolio Risk Calculator

The task was clear: take a portfolio dictionary and compute post-crash value, runway months, ruin test, largest risk asset, and concentration warning.

My approach with Claude was to prompt it in three stages. First I asked it to design clean data models using Python dataclasses for Asset and Portfolio so the logic would be separated from the raw dictionary format. Then I asked it to write the core compute_risk_metrics function using those models. Finally I asked it to add the bonus features: the moderate crash scenario at 50% of expected crash, and a CLI bar chart with no external libraries.

One decision I made myself was to add the crash_loss_magnitude method on the Asset class so that ranking assets by risk contribution was a clean one-liner, instead of doing inline math in the main function. Claude had written it inline and I asked it to refactor that into the model.

The side-by-side comparison between severe and moderate scenarios was the part I found most satisfying to build because it makes the output actually useful to a wealth manager rather than just technically correct.

Nothing in Task 01 blocked me seriously. The math is standard and the display logic is straightforward once the data model is clean.

---

## Task 02 — Live Market Data Fetch

The requirement was to fetch prices for at least one stock/index and one crypto using free public APIs, display them in a formatted table, and handle failures gracefully.

I chose BTC, NIFTY 50, and Gold. I used yfinance as the primary source for all three since it covers all of them, and added dedicated fallbacks: CoinGecko for BTC if yfinance fails, Sensex via yfinance as a fallback for NIFTY, and the SGOL ETF as a fallback for Gold futures.

My prompt to Claude was to build a fetcher where each asset has its own function with its own primary and fallback logic, and a central orchestrator that calls all three independently so one failure never blocks the others. I specifically asked Claude to use typed dataclasses for the result and to log at the right levels (debug vs warning vs error) rather than just printing.

The thing I added myself was the ultimate safety net try/except around each fetcher call in the orchestrator. Claude had the individual fetchers handling their own errors but the orchestrator itself could still crash if something unexpected happened inside a fetcher. I caught that gap and asked Claude to add a final layer.

Gold pricing required one small decision: yfinance returns GC=F (COMEX gold futures) in USD per troy ounce, so I converted it to USD per gram by dividing by 31.1035. I added a comment explaining this so it is not a magic number.

---

## Task 03 — AI-Powered Portfolio Explainer

This was the hardest task and the one where I genuinely got stuck.

The task asked for a script that takes a portfolio, sends it to an LLM, and gets back a plain-English explanation with a summary, one strength, one recommendation, and a verdict of Aggressive, Balanced, or Conservative.

My first attempt was with Gemini via Google AI Studio. The free tier kept hitting quota limits almost immediately, even on light usage. I switched to OpenAI and ran into the same problem: the free credits from the trial were exhausted faster than expected and the paid tier required a card. I spent time on this and it was genuinely frustrating.

The fix came when I found Groq. Groq offers a completely free tier with 14,400 requests per day, no credit card required, and an OpenAI-compatible API which meant I barely had to change my code. I used the llama-3.1-8b-instant model which is fast and follows structured instructions reliably.

For the prompt engineering I went through three iterations. My first attempt was a single flat prompt asking for a plain-English explanation. The output was inconsistent in length and had no parseable structure. My second attempt asked for JSON output. Llama kept wrapping the JSON in markdown fences and the values inside sometimes broke parsing. My final approach was a system and user prompt split with XML tags for each field. XML turned out to be the most reliable format because it survives fencing issues, whitespace, and escaped characters. Temperature 0.4 was the other key decision: lower than that and the output got robotic, higher and the structure got inconsistent.

The most important architectural decision was to do all the arithmetic myself before calling the LLM and pass the finished numbers in the prompt. LLMs are unreliable at arithmetic and I did not want hallucinated calculations in a financial product. The prompt explicitly tells the model to trust the numbers and not recalculate.

I also implemented both bonus features: configurable tone with three distinct personas (beginner, experienced, expert) that change the system prompt, and a second LLM call that critiques the first explanation for accuracy and omissions. The critique call uses a completely different persona so it gives an independent perspective rather than just agreeing with itself.

---

## Task 04 — SIP Goal Planner CLI

For the open problem I built a SIP (Systematic Investment Plan) calculator CLI.

My thinking was that Timecell serves HNI Indian families and the most common anxiety for these families is not which stock to pick but whether they are saving enough for their children's futures. SIP planning is the most searched financial query in India and yet most online calculators are single-input single-output tools with no context. I wanted to build something that felt like a conversation with an advisor.

The tool takes a goal amount, existing savings, time horizon, and expected return. It computes the required monthly SIP using the standard future value of annuity formula, separates out what the existing lump sum does on its own versus what the SIP adds, and shows a year-by-year growth table with ASCII progress bars that change colour as you approach the goal.

I added five preset goals (Child's Education, Wedding, Retirement, Property, Vacation) so a user can be up and running in under ten seconds without typing anything. The tool also accepts Indian formats like 50L, 1Cr, 1.5cr naturally because that is how people in India actually think about money.

The advisor insights section at the end was my own idea. Instead of just showing numbers I convert the monthly SIP into a daily cost, show the wealth multiplier, and suggest what a 10% annual step-up would mean for the starting SIP. These are the things a real relationship manager would say in a meeting.

I prompted Claude to give me the math function first, then the display layer separately, then the preset system, and finally asked it to merge everything with consistent styling. The step-up insight calculation was something I added after the merge because I felt the insights section was missing one practically useful point.

The script has zero external dependencies and runs on pure Python stdlib which means it works anywhere instantly.

---

## What Was the Hardest Part

Task 03 was the hardest by a significant margin, specifically the API access problem. The math and code were not the issue. Getting a working free LLM API that did not require a credit card and had a reasonable rate limit took real time to figure out. Once I found Groq that problem disappeared but I probably spent two hours on that alone.

The second hardest part was the prompt engineering for Task 03. Getting the LLM to return consistently structured output that could be parsed programmatically without breaking took three distinct iterations. The shift from JSON to XML was the unlock.

---

## Repository Structure

task01/portfolio_risk.py — Portfolio Risk Calculator with dual crash scenarios and bar chart

task02/market_fetcher.py — Live market data fetcher with primary and fallback APIs

task03/portfolio_explainer.py — AI-powered portfolio explainer using Groq and llama-3.1-8b-instant

task04/sip_planner.py — SIP Goal Planner CLI

---
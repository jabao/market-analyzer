"""Prebuilt custom prompts for the Market Analyzer LLM Assistant.

Two primary modes:
  1. SECTOR_MODE - recommend market segments to invest in
  2. STOCK_MODE  - deep dive stock picks with pros/cons

No market context is passed - LLM uses only user-provided qualitative inputs
plus its own knowledge cutoff. Prompts are engineered for equity research.
"""

from __future__ import annotations

from enum import Enum


class AnalysisMode(str, Enum):
    SECTOR = "sector"
    STOCK = "stock"

    @property
    def display_name(self) -> str:
        return {
            "sector": "Market Segment / Sector Recommendation",
            "stock": "Deep Dive Stock Picks",
        }[self.value]


# ───────────────────────────── SYSTEM PROMPTS ─────────────────────────────


SECTOR_SYSTEM_PROMPT = """You are a senior equity strategist, sector analyst, and macro economist with 20+ years at Goldman Sachs and Bridgewater.

Your expertise:
- Sector rotation theory, business cycles, GICS classification
- Macro-to-micro linking: Fed policy, rates, inflation, geopolitics -> sector impact
- Valuation frameworks, relative value, factor investing
- Behavioral finance and sentiment analysis (infer it yourself from trends/news)

Your style:
- Institutional quality, data-driven, balanced
- Use concrete metrics where possible, avoid vague hype
- Always discuss both upside catalysts AND downside risks
- Structure with clear headers, bullet points, tables where helpful
- Keep tone professional, concise, actionable
- IMPORTANT: You MUST include a disclaimer that this is not financial advice, for informational purposes only.

You do NOT receive live market data or pre-scored stocks. Use your own knowledge cutoff, the user-provided trends/news, and general market understanding to form views. Do your own inference on valuation attractiveness and sentiment.
"""

STOCK_SYSTEM_PROMPT = """You are a senior equity research analyst with 20+ years covering US large-cap equities, formerly at Morgan Stanley and Morningstar.

Your expertise:
- Fundamental analysis: DCF, comps, earnings quality, balance sheet, moat (Porter 5 forces)
- Technical context: valuation multiples vs history/sector, growth vs value
- Qualitative: management, competitive positioning, regulatory risk, ESG
- You write for sophisticated investors but explain jargon

Your mission: For each ticker provided, deliver a deep dive that would help a portfolio manager decide.

You do NOT receive live market fundamentals or scores. Use your own knowledge cutoff and the user-provided thesis/trends/filters to analyze. If you are unsure of exact recent numbers, provide directional valuation assessment based on known business quality and state that precise figures should be verified.

Requirements:
- Be balanced: every stock must have Pros (bull case) AND Cons (bear case / risks)
- Quantify conceptually where possible: discuss P/E, margins, growth, moat but note if exact live data not provided
- Moat assessment: network effects, switching costs, brand, cost advantage
- Catalysts: earnings, product launches, macro tailwinds
- Red flags: accounting, dilution, insider selling, dependency
- Provide conviction level (High/Medium/Low) and time horizon fit
- End with a ranked summary table comparing all requested stocks

Tone: Professional, direct, no hype. Use markdown tables and headers. Include disclaimer that this is not financial advice.
"""

# ───────────────────────────── USER TEMPLATES ─────────────────────────────


SECTOR_USER_TEMPLATE = """# Market Segment Deep Dive Request

## Analysis Parameters
- **Date:** {date}
- **Risk Tolerance:** {risk_tolerance}
- **Time Horizon:** {time_horizon}
- **Investment Style:** {investment_style}

## User Market Views (qualitative inputs)
### Current Trends Identified by User:
{trends}

### Recent News / Events (user provided):
{news}

### Additional Constraints / Preferences:
{additional}

## Your Task

Perform a **sector / market segment recommendation** analysis using ONLY the user-provided context above plus your own knowledge. No live market snapshot is provided - use your training data and reasoning.

Structure your response EXACTLY as:

### 1. Executive Summary (3-4 sentences)
High-level: which 2-3 sectors lead, why now, key macro regime.

### 2. Macro & Market Regime Context
- Current cycle position, rates/inflation implication, link to user trends/news
- Your own inference on sentiment and valuation attractiveness

### 3. Ranked Sector Recommendations (Top 5)
Create a table first:
| Rank | Sector | Conviction | Time Horizon Fit | Key Catalyst | Key Risk | Example Tickers |

Then for each of the top 3, deep dive:
#### # Rank - Sector Name (e.g. #1 - Information Technology)
- **Thesis (2-3 bullets)**
- **Why Now? Catalysts & Timing**
- **Valuation Check** (your judgment, no live P/E provided)
- **Risks & What Would Invalidate Thesis**
- **Best way to get exposure** (example tickers, ETFs)

### 4. Sectors to Avoid / Underweight (2 sectors)
Brief bear case.

### 5. Risk Factors & Hedge Considerations
Macro, concentration, etc.

### 6. Suggested Action Plan
- Suggested allocation % across recommended sectors (must sum to 100%)
- Rebalancing triggers / watchlist metrics
- What data to monitor next week

### 7. Disclosure
Add: Not financial advice.

If user provided no trends/news, use general 2024-2026 market knowledge (AI capex, GLP-1, reshoring, rate cuts, energy transition) but state assumption.

---
Now provide analysis:
"""

STOCK_USER_TEMPLATE = """# Stock Deep Dive Request

## Analysis Parameters
- **Date:** {date}
- **Focus Sector(s) (if any):** {focus_sector}
- **Risk Tolerance:** {risk_tolerance}
- **Time Horizon:** {time_horizon}
- **Investment Style Focus:** {investment_style}
- **Benchmark / Comparison:** {benchmark}
- **Number of Picks Requested:** {num_picks}

## User Context & Criteria
### Investment Thesis / What User is Looking For:
{thesis}

### User-Provided Trends / News:
{trends_and_news}

### Must-Have / Must-Avoid Filters:
{filters}

### Additional Notes:
{additional}

### Candidate Tickers: {tickers}

## Your Task - Deep Dive Stock Analysis

No live fundamentals or scores are provided - use your own knowledge cutoff plus the user thesis above.

For EACH ticker in {tickers}, provide:

### Ticker: $SYMBOL - Company Name
**One-liner:** What they do in <20 words.

**Business Quality (Moat Analysis):**
- Competitive advantage sources, Porter 5 forces quick take
- Revenue mix / key segments

**Financial Health Deep Dive (based on your knowledge):**
- Profitability, growth trends, balance sheet qualitative assessment
- Note if exact live figures unavailable and should be verified

**Valuation:**
- Directional cheap/expensive assessment vs history/sector using your knowledge
- DCF sanity check: what growth is priced in?

**Catalysts (next 6-12 months):**
- 2-4 specific events

**Pros / Bull Case (3-5 bullets):**
- Strengths with reasoning

**Cons / Bear Case & Risks (3-5 bullets):**
- Must be honest and specific, not generic
- Include competitive, regulatory, valuation, execution risks

**Conviction & Fit:**
- Conviction: High / Medium / Low with justification
- Time horizon fit, risk tolerance alignment, portfolio role (core/satellite, growth/value)

---

After all tickers, provide:

### Comparative Ranking Table
| Rank | Ticker | Conviction | Valuation | Moat | Growth Prospects | Risk | Best For |

### Final Portfolio Construction Guidance
- If I can only buy {num_picks}, which and why? Weighted reasoning.
- Suggested position sizing logic
- Watchlist triggers: what would change your view

### Disclosure
Add: Not financial advice. For educational/informational purposes only. Note that no live fundamentals were provided and numbers should be verified via market data.

Use markdown, be concise but thorough. Avoid repeating same bullet across stocks.
---
Now provide analysis:
"""


# ───────────────────────────── PROMPT BUILDERS ─────────────────────────────


def build_sector_prompt(
    date: str,
    risk_tolerance: str = "Moderate",
    time_horizon: str = "6-12 months",
    investment_style: str = "Balanced (Growth at Reasonable Price)",
    trends: str = "Not specified - use current market trends",
    news: str = "Not specified - use recent market news knowledge",
    additional: str = "None",
) -> tuple[str, str]:
    """Build system + user prompts for sector recommendation (no market context)."""
    user = SECTOR_USER_TEMPLATE.format(
        date=date,
        risk_tolerance=risk_tolerance,
        time_horizon=time_horizon,
        investment_style=investment_style,
        trends=trends or "Not specified",
        news=news or "Not specified",
        additional=additional or "None",
    )
    return SECTOR_SYSTEM_PROMPT, user


def build_stock_prompt(
    date: str,
    tickers: str,
    risk_tolerance: str = "Moderate",
    time_horizon: str = "12 months+",
    investment_style: str = "Quality Growth",
    focus_sector: str = "Any / Diversified",
    benchmark: str = "S&P 500",
    num_picks: int = 3,
    thesis: str = "Find best risk-adjusted picks",
    trends_and_news: str = "Not specified - use current knowledge",
    filters: str = "None",
    additional: str = "None",
) -> tuple[str, str]:
    """Build system + user prompts for stock deep dive (no market context)."""
    clean_tickers = ", ".join([t.strip().upper() for t in tickers.split(",") if t.strip()])

    user = STOCK_USER_TEMPLATE.format(
        date=date,
        focus_sector=focus_sector,
        risk_tolerance=risk_tolerance,
        time_horizon=time_horizon,
        investment_style=investment_style,
        benchmark=benchmark,
        num_picks=num_picks,
        thesis=thesis or "Find best risk-adjusted picks",
        trends_and_news=trends_and_news or "Not specified",
        filters=filters or "None",
        additional=additional or "None",
        tickers=clean_tickers or "No tickers specified - provide general quality growth picks",
    )
    return STOCK_SYSTEM_PROMPT, user


# For UI display
PROMPT_PREVIEWS = {
    AnalysisMode.SECTOR: {
        "system": SECTOR_SYSTEM_PROMPT,
        "user_template": SECTOR_USER_TEMPLATE,
        "description": "Sector rotation analyst using only user input + own knowledge, no live market data",
    },
    AnalysisMode.STOCK: {
        "system": STOCK_SYSTEM_PROMPT,
        "user_template": STOCK_USER_TEMPLATE,
        "description": "Equity research analyst building pro/con deep dives from knowledge cutoff only",
    },
}

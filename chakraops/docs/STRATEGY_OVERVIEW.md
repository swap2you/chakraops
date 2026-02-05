*This document describes intent and philosophy, not implementation details.*

# ChakraOps Strategy Overview

## 1. What ChakraOps Is Optimizing For

**Primary goal:** Consistent options premium income with capital preservation. The system is built for an end-of-day (EOD) options strategy: selling cash-secured puts (CSP) and covered calls (CC) on a fixed universe of names, with an emphasis on not losing capital and avoiding reckless risk.

**Secondary goals:**
- Filtering the universe so only symbols that pass data-quality and liquidity gates are considered.
- Aligning with market regime (e.g., not opening new CSP when the regime is RISK_OFF).
- Providing a clear verdict (ELIGIBLE vs HOLD vs BLOCKED) and reason so the operator can decide whether to trade.

**Explicitly de-prioritized:**
- High-risk alpha or speculative directional bets.
- Intraday timing or day-trading.
- Predicting price direction; the system screens for *opportunity* and *quality*, not for “this will go up or down.”

---

## 2. Asset Universe Philosophy

**Why these symbols exist in the universe:** The universe is defined in `config/universe.csv` and is the single source of truth for which symbols are evaluated. It typically includes liquid, optionable names (e.g., large-cap equities and a few ETFs such as SPY and QQQ). Symbols are chosen by the operator; the system does not add or remove symbols automatically.

**What “stock quality” means conceptually:** A symbol is considered to have sufficient stock quality when it has usable price data, acceptable data completeness (e.g., price and, where required, bid/ask/volume or waived equivalents), and passes any regime or risk-posture checks. Missing or invalid data can result in HOLD or BLOCKED so the system does not recommend a trade on bad inputs.

**ETFs like SPY/QQQ:** They are part of the same universe and are evaluated with the same pipeline. SPY and QQQ are also used as inputs for the market-regime engine (e.g., trend and RSI). They are not given a different *strategy* treatment; they are simply names in the list that may qualify or not based on the same gates.

---

## 3. Strategy Types Supported

**Cash-Secured Puts (CSP):** Selling a put option with cash reserved to buy the stock if assigned. Used when the operator is willing to own the underlying at the strike price. The system looks for puts in a target delta range (e.g., around -0.25) and a target DTE window (e.g., 21–45 days). CSP is the default “entry” strategy when there is no existing position in the symbol.

**Covered Calls (CC):** Selling a call option against shares already held. CC is only relevant when the operator has a long position in the underlying. The system does not recommend opening a new CC if there is already an open CC; it may block or deprioritize a second CC on the same name.

**What makes each strategy eligible:** CSP is eligible when the symbol passes stock quality and options liquidity gates and there is no open CSP (or blocking position) for that symbol. CC is eligible when the operator is assumed or known to hold shares and the same quality and liquidity bars are met, and no open CC exists for that symbol.

**Why the system may show both but select one:** The UI or pipeline may surface both CSP and CC as *possible* strategies, but position-awareness rules (e.g., “no open CSP” or “shares held”) determine which one is actually recommended. When position state is unknown, the system may show both with a note that the user should confirm which applies.

---

## 4. Capital & Risk Posture

**Conservative posture:** The system is designed with a conservative risk posture. That means stricter gates (e.g., data completeness, liquidity, regime) and no automatic execution; the operator always decides whether to place a trade. High-notional names are not “banned,” but they can be deprioritized in sort order (e.g., by score and then by CSP notional) so that very large capital requirements do not float to the top solely on score.

**Capital allocation logic:** Confidence bands (A, B, C) suggest a *relative* capital allocation (e.g., Band A might suggest a higher percentage per position than Band C). These are hints (e.g., 2%–5% bands), not mandates. The intent is to size positions in line with conviction and data quality.

**Why high-notional names are penalized or deprioritized:** A name like COST with a high share price implies a large notional per contract (strike × 100). Default sorting can put “score first, then CSP notional ascending” so that lower-notional candidates appear before huge ones when scores are similar. This avoids recommending a trade that would require disproportionate capital relative to the rest of the universe.

---

## 5. Evaluation Stages (Conceptual, Not Code)

Evaluation is done in stages. Each stage can block or downgrade a symbol before the next.

**Stage 0: Run context & market state**  
The system establishes run context (e.g., last evaluation time, market phase) and market regime (e.g., RISK_ON, NEUTRAL, RISK_OFF from index rules). This context is used later to cap scores or force HOLD (e.g., in RISK_OFF). *What it prevents:* Acting as if “all is well” when the broader market context is hostile. *Failure means:* The run may still complete, but verdicts and scores are adjusted (e.g., all HOLD in RISK_OFF).

**Stage 1: Stock quality gate**  
Each symbol is checked for price, data completeness (e.g., bid/ask/volume where required or explicitly waived), and IV rank. Missing price is treated as fatal; missing other fields may be non-fatal (e.g., waived when options liquidity is confirmed). *What it prevents:* Recommending a trade on a symbol with no price or clearly incomplete data. *Failure means:* The symbol does not advance to options evaluation (HOLD or BLOCKED at Stage 1).

**Stage 2: Strategy eligibility gate**  
Position-awareness is applied: open CSP or CC can block a new CSP or second CC. Regime and risk posture may also block or cap. *What it prevents:* Suggesting a new CSP when one is already open, or a second CC when one is open. *Failure means:* Verdict remains HOLD or BLOCKED with a reason (e.g., position already open).

**Stage 3: Options liquidity gate**  
The system checks that there are option contracts with usable bid/ask and open interest (e.g., from delayed or live options data). If options data is missing or too thin, the symbol is not considered tradeable. *What it prevents:* Recommending a trade that cannot be executed in size with reasonable spread. *Failure means:* ELIGIBLE is not reached; reason often cites missing or insufficient options liquidity.

**Stage 4: Trade construction**  
For symbols that pass the prior stages, a specific contract (e.g., strike, expiry) may be selected (e.g., by target delta and DTE). This is the “what to trade” step. *What it prevents:* Nothing by itself; it only runs when earlier gates pass. *Failure means:* If no contract fits criteria, the symbol may still be ELIGIBLE with a generic “options liquidity confirmed” message but without a single recommended contract.

---

## 6. Scoring & Bands (High-Level)

**What the score represents:** A relative desirability rank (e.g., 0–100) based on data quality, regime, liquidity, and other factors. It is *not* a probability of success or a guarantee. Higher score means “relative to the rest of the universe, this symbol passed more checks and looks better on the current filters.”

**Why scores may cluster:** Many symbols may get similar scores (e.g., same regime, similar data completeness). When that happens, the system may log that scores are “flattened” so the operator knows that ranking is not highly differentiated. Sort order can then use secondary criteria (e.g., CSP notional) to break ties.

**What Band C means today:** Band C is the lowest confidence band. It is used for HOLD verdicts, BLOCKED/UNKNOWN, or ELIGIBLE with lower data completeness or non–RISK_ON regime. It suggests a smaller suggested capital allocation (e.g., 2%) and means “proceed with extra caution if you trade at all.”

**Why Band A/B may be rare by design:** Band A typically requires RISK_ON regime, high data completeness, strong liquidity, and ELIGIBLE verdict. Band B is used for NEUTRAL regime or minor data gaps. Because the system is conservative and regime is often NEUTRAL or RISK_OFF, many symbols end up in Band C; Band A and B are reserved for the clearest, highest-conviction setups.

---

## 7. What ChakraOps Does NOT Do

- **No prediction:** It does not predict whether a stock will go up or down. It screens for opportunity and data quality only.
- **No earnings gambling:** It does not intentionally open positions right before earnings for a “binary” bet. Earnings blocks or filters may exist to avoid recommending a trade when an event is imminent.
- **No intraday timing:** The design is EOD. Decisions are based on snapshot or delayed data suitable for end-of-day review, not for intraday entry/exit timing.
- **No discretionary overrides:** The operator cannot “override” the pipeline inside the app to force ELIGIBLE or ignore a gate. The human decides *whether* to trade; the system decides *what* passed its rules.

---

## 8. How a Human Should Use This System

**How often to check:** The system can run evaluations on a schedule (e.g., every 15 minutes when the market is open) and/or nightly. Checking once after market close or at a fixed time is enough for an EOD strategy; more frequent checks do not change the logic, only how fresh the last run is.

**What to do when something is ELIGIBLE:** Treat it as a *candidate*, not an order. Review the symbol, strike, expiry, and reason. If you agree with the setup and risk, you can place the trade in your broker. The system does not execute; it recommends.

**What HOLD actually implies:** The symbol did not pass all gates (e.g., data incomplete, liquidity insufficient, regime not favorable, or position already open). It is not “bad”; it means “no recommendation right now.” You can still trade it manually if you have other information.

**What NOT to do as a user:** Do not treat ELIGIBLE as a signal to trade without review. Do not assume that missing data (e.g., N/A in the UI) is “fine” unless the system explicitly marks it as waived with a reason. Do not ignore BLOCKED or position-open reasons. Do not use the system for intraday timing or as a substitute for your own risk and position sizing.

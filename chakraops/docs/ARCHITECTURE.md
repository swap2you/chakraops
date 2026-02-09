# ChakraOps Architecture

This document explains **how the system works** (evaluation pipeline, strategy model, risk & gating flow, decision lifecycle). It contains no operational instructions—for those, use [RUNBOOK.md](./RUNBOOK.md). For data rules, use [DATA_CONTRACT.md](./DATA_CONTRACT.md).

---

## 1. What ChakraOps Is

**Primary goal:** Consistent options premium income with capital preservation. The system supports an end-of-day (EOD) options workflow: selling cash-secured puts (CSP) and covered calls (CC) on a fixed universe, with emphasis on not losing capital and avoiding reckless risk.

**What it does:**
- Filters the universe so only symbols that pass data-quality and liquidity gates are considered.
- Aligns with market regime (e.g. no new CSP when regime is RISK_OFF).
- Produces a clear verdict (ELIGIBLE / HOLD / BLOCKED) and reason so the operator can decide whether to trade.
- Ranks candidates by a composite score and confidence band (A/B/C) for relative capital hints.

**What it does not do:**
- Predict price direction; it screens for *opportunity* and *quality*, not “this will go up or down.”
- High-risk alpha or intraday timing; design is EOD.
- Automatic execution; the operator always decides whether to place a trade. No broker automation.

---

## 2. Mental Model: Pipeline in Order

Evaluation runs in a fixed order. Each stage can block or downgrade a symbol before the next.

| Stage | Purpose | Why it exists |
|-------|---------|----------------|
| **Universe** | Define which symbols are evaluated. | Single source of truth (`config/universe.csv`); no auto-add/remove. |
| **Market regime** | Global filter from index (SPY/QQQ) technicals. | Prevents acting as if “all is well” when context is hostile; RISK_OFF blocks CSP and caps scores. |
| **Stock quality** | Minimum required equity data (price, IV rank, bid/ask/volume where required). | Prevents recommending a trade on no price or clearly incomplete data. |
| **Strategy eligibility** | Position and regime: no new CSP if open CSP; no second CC if open CC; regime blocks. | Prevents suggesting a new CSP when one is already open, or a second CC. |
| **Options liquidity** | Confirm usable option contracts (chain, bid/ask/OI). | Prevents recommending a trade that cannot be executed with reasonable spread. Can waive upstream stock bid/ask gaps when options liquidity is confirmed. |
| **Trade construction** | Select recommended contract (target delta, DTE window, liquidity threshold). | “What to trade” for symbols that passed prior gates. |
| **Score & band** | Relative score (0–100) and confidence band (A/B/C). | Sort order and capital hints; not a probability of success. |

Implementation uses a **2-stage evaluator** (Stage 1: stock quality + regime; Stage 2: options chain + liquidity + contract selection). The stages above map to that and to the UI (Pipeline / Strategy details). See [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) for per-stage inputs, outputs, failure modes, and verification paths.

---

## 3. Strategy Types

**CSP (Cash-Secured Put):** Sell a put with cash reserved to buy the stock if assigned. Used when the operator is willing to own the underlying at the strike. The system looks for puts in a target delta range (e.g. around -0.25) and DTE window (e.g. 21–45 days). CSP is the default “entry” strategy when there is no existing position.

**CC (Covered Call):** Sell a call against shares already held. CC is only relevant when the operator has a long position. The system does not recommend a second CC on the same name.

**Eligibility:** CSP is eligible when the symbol passes stock quality and options liquidity and there is no open CSP (or blocking position). CC is eligible when the operator is assumed or known to hold shares and the same bars are met, and no open CC exists. Position-awareness and regime determine which strategy is actually recommended; when position state is unknown, the UI may show both with a note to confirm.

**Options-layer design (contract selection):** For symbols passing stock-level gates, the options layer requires a chain (or snapshot-time view) with expirations in the DTE window, strikes around the current price, and per contract: bid, ask, delta, IV (optional: gamma, vega, theta). Delta is used for strike/contract selection (target delta range); other Greeks are optional or execution-time only. Snapshot is authoritative for screening; live data is for execution-time checks only and must not override screening. Rejection reasons at the options layer include: no put/call in delta range, no expiry in DTE window, no valid strike, premium too low, chain unavailable. See [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) and [ORATS_OPTION_DATA_PIPELINE.md](./ORATS_OPTION_DATA_PIPELINE.md) for implementation detail.

---

## 4. Scoring and Bands

**What the score is:** A relative desirability rank (0–100) from data quality, regime, liquidity, strategy fit, and capital efficiency. It is *not* a probability of success. Higher score means “relative to the rest of the universe, this symbol passed more checks and looks better on the current filters.”

**Why scores may cluster:** Many symbols can get similar scores (same regime, similar completeness). Sort order then uses secondary criteria (e.g. CSP notional ascending) so high-notional names do not float to the top solely on score.

**Components (from config):** Composite score is a weighted sum of: data_quality, regime, options_liquidity, strategy_fit, capital_efficiency. Weights and thresholds (e.g. notional % warn/heavy/cap, high-price penalty) are in `config/scoring.yaml`. Account equity can be set via config or env for notional %; if unset, only high underlying price penalty applies. See [SCORING_AND_BANDING.md](./SCORING_AND_BANDING.md) for exact keys and defaults.

**Bands:**
- **Band A:** ELIGIBLE, score ≥ band_a_min (e.g. 78), RISK_ON, data_completeness and liquidity gates met, no position open. Highest suggested capital % (e.g. 5%).
- **Band B:** ELIGIBLE, score ≥ band_b_min (e.g. 60), but any gate not meeting A (e.g. NEUTRAL regime, completeness &lt; 0.9, position open).
- **Band C:** Not ELIGIBLE, or score &lt; band_b_min, or data_completeness &lt; 0.75. Lowest suggested capital % (e.g. 2%); band_reason always explains why.

Band C is never a silent default; band_reason is always set. RISK_OFF caps score at 50; NEUTRAL caps at 65; Band A is only available in RISK_ON.

---

## 5. Asset Universe and Data

**Universe:** Defined in `config/universe.csv` (symbol, optional strategy_hint, notes). The system does not add or remove symbols automatically. ETFs like SPY/QQQ are in the same universe and evaluated with the same pipeline; they also feed the market-regime engine.

**Snapshot is authoritative:** All screening decisions use snapshot-based (or snapshot-timestamped) price, IV rank, and options chain. Live market data may augment but must not override snapshot for “what is a candidate.” Realtime is shadow-only for screening.

**Greeks policy:** Delta is required for CSP/CC contract selection when the options chain is used. Gamma, vega, theta are optional (e.g. execution-time or roll logic). Off-hours, only snapshot-time chain or cached Greeks at snapshot timestamp are used; no live feed drives the decision.

---

## 6. What Must Never Auto-Execute

- Sending orders to a broker or exchange must **not** be triggered by the strategy layer. Any “execute” or “place order” is operator-driven.
- Alerts and suggestions (e.g. “CSP candidate ready”) are allowed; order routing is not.
- Overwriting snapshot or regime with realtime data for **decisions** is forbidden.

---

## 7. Further Reading

| Document | Purpose |
|----------|---------|
| [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) | Stage-by-stage implementation: inputs, outputs, failure modes, reason codes, where to verify. |
| [SCORING_AND_BANDING.md](./SCORING_AND_BANDING.md) | Config keys, component weights, notional % and high-price penalties, band limits. |
| [ORATS_OPTION_DATA_PIPELINE.md](./ORATS_OPTION_DATA_PIPELINE.md) | ORATS data flow and endpoints. |
| [DATA_CONTRACT.md](./DATA_CONTRACT.md) | Required vs optional data, staleness, BLOCKED/WARN/PASS, overrides. |
| [PHASE3_PORTFOLIO_AND_RISK.md](./PHASE3_PORTFOLIO_AND_RISK.md) | Portfolio and risk limits. |

Historical strategy-audit and validation reports (signal contract, pipeline gates, subscription limitations) are in [history/](./history/); they are not required for operation but can clarify design choices and data caveats.

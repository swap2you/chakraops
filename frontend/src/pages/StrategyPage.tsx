/**
 * Strategy page — Premium interactive learning experience for ChakraOps.
 * Expert-level explainer teaching the evaluation pipeline, decision logic,
 * and interpretation of outputs. Designed for advanced users.
 */
import { useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Globe,
  Activity,
  BarChart2,
  Target,
  Layers,
  Wrench,
  Gauge,
  X,
  ChevronDown,
  Zap,
  Shield,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Info,
  BookOpen,
  Lightbulb,
  ArrowRight,
  Ban,
  Eye,
  Scale,
  User,
  Clock,
  DollarSign,
  XOctagon,
  HelpCircle,
  Play,
  RefreshCw,
  Lock,
  Unlock,
  MessageCircleWarning,
  Square,
} from "lucide-react";
import { getResolvedUrl } from "../data/apiClient";
import { ENDPOINTS } from "../data/endpoints";

/* ═══════════════════════════════════════════════════════════════════════════
   TYPES & DATA
   ═══════════════════════════════════════════════════════════════════════════ */

type GateType = "hard" | "soft" | "ranking";
type FailureEffect = "BLOCKED" | "HOLD" | "DEPRIORITIZED" | "NONE";

interface DecisionLens {
  decision: string;
  gateType: GateType;
  failureEffect: FailureEffect;
  operatorTakeaway: string;
}

interface StageDetail {
  id: string;
  stageNumber: number;
  title: string;
  icon: React.ElementType;
  color: string;
  summary: string;
  purpose: string;
  inputs: string[];
  outputs: string[];
  failureModes: { condition: string; result: string }[];
  example: { scenario: string; outcome: string };
  decisionLens: DecisionLens;
  tip: string;
}

const PIPELINE_STAGES: StageDetail[] = [
  {
    id: "universe",
    stageNumber: 1,
    title: "Universe",
    icon: Globe,
    color: "from-blue-500 to-cyan-500",
    summary: "Define which symbols to evaluate",
    purpose: "Single source of truth for evaluated symbols. The operator controls what enters the pipeline — the system never adds or removes symbols automatically. This ensures intentionality: you evaluate only what you've deliberately chosen to track.",
    inputs: ["config/universe.csv (symbol, strategy_hint, notes)"],
    outputs: ["Symbol list for downstream evaluation"],
    failureModes: [
      { condition: "Empty universe file", result: "No symbols evaluated; run completes with zero results" },
      { condition: "Invalid symbol format", result: "Symbol skipped with warning in logs" },
      { condition: "Duplicate entries", result: "Deduplicated; only first occurrence kept" },
    ],
    example: {
      scenario: "Universe: SPY, QQQ, AAPL, MSFT, GOOGL (5 symbols)",
      outcome: "All 5 enter Stage 1. Each evaluated independently through the full pipeline.",
    },
    decisionLens: {
      decision: "Which symbols are candidates for evaluation?",
      gateType: "hard",
      failureEffect: "NONE",
      operatorTakeaway: "If a symbol isn't in the universe, it doesn't exist to the system. Add it explicitly if you want it evaluated.",
    },
    tip: "Quality over quantity. A focused universe of 20–50 liquid names is more actionable than 500 tickers with thin options.",
  },
  {
    id: "regime",
    stageNumber: 2,
    title: "Market Regime",
    icon: Activity,
    color: "from-violet-500 to-purple-500",
    summary: "Assess macro market conditions",
    purpose: "Determine if the broader market environment supports opening new premium-selling positions. Regime classification uses index data (SPY/QQQ) to identify hostile conditions where selling CSP would be fighting the tape. This is a global filter: all symbols are affected equally.",
    inputs: ["SPY/QQQ daily price", "EMA(20), EMA(50) crossover", "RSI(14)", "ATR(14) for volatility context"],
    outputs: ["RISK_ON (favorable)", "NEUTRAL (proceed with caution)", "RISK_OFF (defensive)"],
    failureModes: [
      { condition: "Index data unavailable", result: "Defaults to NEUTRAL; logs warning" },
      { condition: "RISK_OFF detected", result: "All scores capped at 50; CSP blocked globally" },
      { condition: "NEUTRAL detected", result: "Scores capped at 65; Band A unavailable" },
    ],
    example: {
      scenario: "SPY price < EMA(50), RSI(14) = 35, declining trend",
      outcome: "RISK_OFF → Even AAPL with perfect data and liquidity cannot reach ELIGIBLE for CSP",
    },
    decisionLens: {
      decision: "Is the market environment safe for new premium-selling positions?",
      gateType: "hard",
      failureEffect: "HOLD",
      operatorTakeaway: "In RISK_OFF, the system protects you from yourself. Wait for conditions to improve before deploying capital.",
    },
    tip: "RISK_OFF is not a bug — it's the system doing its job. Avoiding drawdowns in hostile markets is more valuable than chasing premium.",
  },
  {
    id: "quality",
    stageNumber: 3,
    title: "Stock Quality",
    icon: BarChart2,
    color: "from-emerald-500 to-green-500",
    summary: "Validate data completeness & integrity",
    purpose: "Ensure each symbol has the minimum required data to make a sound evaluation. Missing price is fatal. Missing bid/ask or volume may be waived if downstream options liquidity confirms tradeability. IV rank informs scoring but isn't blocking. This gate prevents garbage-in-garbage-out.",
    inputs: ["Current price (required)", "Bid/Ask spread (waivable)", "Volume (waivable)", "IV Rank (scoring input)"],
    outputs: ["PASS → proceed to eligibility", "FAIL → HOLD with DATA_INCOMPLETE reason"],
    failureModes: [
      { condition: "No price data", result: "BLOCKED — fatal; cannot evaluate" },
      { condition: "Missing bid/ask, not waived", result: "HOLD — DATA_INCOMPLETE" },
      { condition: "Missing bid/ask, options liquidity confirmed", result: "WAIVED — proceeds with note" },
      { condition: "IV rank unavailable", result: "Score penalized; not blocking" },
    ],
    example: {
      scenario: "DIS: price = $95.50, bid/ask = null, volume = null",
      outcome: "If options liquidity later confirms usable chain, bid/ask waived. Otherwise: HOLD with DATA_INCOMPLETE.",
    },
    decisionLens: {
      decision: "Is there enough data to evaluate this symbol responsibly?",
      gateType: "hard",
      failureEffect: "HOLD",
      operatorTakeaway: "DATA_INCOMPLETE means the system refuses to guess. Fix the data source or accept the waiver path via options confirmation.",
    },
    tip: "Missing ≠ zero. A stock with genuinely zero volume is different from one where volume data wasn't provided. The system tracks the difference.",
  },
  {
    id: "eligibility",
    stageNumber: 4,
    title: "Strategy Eligibility",
    icon: Target,
    color: "from-orange-500 to-amber-500",
    summary: "Apply position & strategy rules",
    purpose: "Check position-awareness constraints: don't suggest a new CSP if one is already open for this symbol; don't suggest a second CC on the same name. Also applies regime-based strategy blocks (e.g., no CSP in RISK_OFF). This gate prevents overexposure and conflicting positions.",
    inputs: ["Open positions journal (symbol, strategy, qty)", "Current regime", "Strategy type being evaluated"],
    outputs: ["ELIGIBLE strategies", "BLOCKED reason (POSITION_ALREADY_OPEN, REGIME_BLOCK)"],
    failureModes: [
      { condition: "Open CSP exists for symbol", result: "New CSP BLOCKED — POSITION_ALREADY_OPEN" },
      { condition: "Open CC exists for symbol", result: "Second CC BLOCKED" },
      { condition: "No shares held for CC", result: "CC NOT_APPLICABLE — CSP may still be eligible" },
      { condition: "RISK_OFF regime + CSP", result: "CSP BLOCKED — REGIME_BLOCK" },
    ],
    example: {
      scenario: "AAPL: Open CSP from 2 weeks ago (not yet expired/closed)",
      outcome: "New CSP on AAPL → BLOCKED with reason POSITION_ALREADY_OPEN. Protects against doubling down.",
    },
    decisionLens: {
      decision: "Is this strategy permissible given current positions and regime?",
      gateType: "hard",
      failureEffect: "BLOCKED",
      operatorTakeaway: "POSITION_ALREADY_OPEN is guardrail, not punishment. Close the existing position or let it expire before the system suggests another.",
    },
    tip: "Position-awareness prevents the common mistake of stacking CSPs on a falling knife. One position per symbol per strategy.",
  },
  {
    id: "liquidity",
    stageNumber: 5,
    title: "Options Liquidity",
    icon: Layers,
    color: "from-pink-500 to-rose-500",
    summary: "Verify tradeable contracts exist",
    purpose: "Confirm that usable option contracts exist with acceptable bid/ask spreads and sufficient open interest. A theoretical opportunity means nothing if you can't execute it at a reasonable price. This gate also enables the waiver path: if options liquidity is strong, upstream stock-level bid/ask gaps can be forgiven.",
    inputs: ["Options chain (strikes, expiries)", "Bid/Ask per contract", "Open interest", "Volume"],
    outputs: ["Liquidity PASS → proceed to construction", "Liquidity FAIL → HOLD with reason"],
    failureModes: [
      { condition: "No options chain available", result: "BLOCKED — NO_CHAIN" },
      { condition: "All strikes have wide spreads (>$0.50 or >10%)", result: "HOLD — LIQUIDITY_WARN" },
      { condition: "Zero open interest at target strikes", result: "HOLD — THIN_MARKET" },
      { condition: "Acceptable liquidity found", result: "PASS — may waive upstream data gaps" },
    ],
    example: {
      scenario: "Small-cap XYZ: options exist, but bid/ask spread = $1.50 on a $2.00 premium",
      outcome: "HOLD — spread too wide. Execution slippage would destroy edge.",
    },
    decisionLens: {
      decision: "Can this trade be executed at a reasonable price?",
      gateType: "hard",
      failureEffect: "HOLD",
      operatorTakeaway: "Liquidity is where theory meets reality. If the system says LIQUIDITY_WARN, respect it — paper gains evaporate in wide spreads.",
    },
    tip: "This gate has a dual role: filtering illiquid names AND enabling waivers for stocks with confirmed options liquidity.",
  },
  {
    id: "construction",
    stageNumber: 6,
    title: "Trade Construction",
    icon: Wrench,
    color: "from-sky-500 to-blue-500",
    summary: "Select the specific contract",
    purpose: "For symbols passing all gates, identify the optimal contract: strike near target delta (~-0.25 for CSP), expiry within DTE window (21–45 days typical). This transforms 'AAPL is eligible' into 'AAPL $180 PUT, 32 DTE, -0.24 delta'. If no contract fits criteria, the symbol remains ELIGIBLE but without a specific recommendation.",
    inputs: ["Options chain", "Target delta (configurable, default ~-0.25)", "DTE window (configurable, default 21–45)", "Premium thresholds"],
    outputs: ["Recommended contract (strike, expiry, delta, premium)", "Or: ELIGIBLE with no specific contract"],
    failureModes: [
      { condition: "No contracts in DTE window", result: "ELIGIBLE but no specific recommendation" },
      { condition: "No strikes near target delta", result: "Best available selected with deviation note" },
      { condition: "Premium below minimum threshold", result: "Contract skipped; next best selected" },
    ],
    example: {
      scenario: "AAPL: 30 DTE options available, strikes at $5 increments",
      outcome: "Recommends AAPL $180 PUT @ -0.24 delta, 32 DTE, $2.15 premium. Specificity enables action.",
    },
    decisionLens: {
      decision: "What exact contract should the operator consider?",
      gateType: "ranking",
      failureEffect: "NONE",
      operatorTakeaway: "The system suggests a specific contract — you decide if the premium and risk/reward fit your criteria.",
    },
    tip: "Construction is the 'what to trade' step. Prior stages determined 'whether to trade'. Both must pass.",
  },
  {
    id: "scoring",
    stageNumber: 7,
    title: "Score & Band",
    icon: Gauge,
    color: "from-indigo-500 to-violet-500",
    summary: "Rank and assign confidence",
    purpose: "Compute a relative desirability score (0–100) for sorting and a confidence band (A/B/C) for capital allocation hints. Score is NOT a probability or prediction — it's a ranking within the current run. Symbols with similar profiles will have similar scores. Band reflects conviction level based on data quality, regime, and liquidity.",
    inputs: ["All prior stage outputs", "Data completeness %", "Regime", "Liquidity strength", "Verdict"],
    outputs: ["Score (0–100)", "Band (A/B/C)", "Suggested capital % hint"],
    failureModes: [
      { condition: "HOLD/BLOCKED verdict", result: "Band C regardless of score" },
      { condition: "RISK_OFF regime", result: "Score capped at 50" },
      { condition: "NEUTRAL regime", result: "Score capped at 65; Band A unavailable" },
      { condition: "Data gaps (even if waived)", result: "Score penalized 5–15 points" },
    ],
    example: {
      scenario: "MSFT: RISK_ON, 100% data completeness, strong liquidity, ELIGIBLE",
      outcome: "Score: 87, Band A → suggests 5% capital allocation. Rare outcome by design.",
    },
    decisionLens: {
      decision: "How does this opportunity compare to others in this run?",
      gateType: "ranking",
      failureEffect: "DEPRIORITIZED",
      operatorTakeaway: "Score is for sorting, not predicting. A score of 85 vs 75 means 'slightly better setup' — not '10% more likely to succeed'.",
    },
    tip: "If many symbols have score 72, that's not a bug — it means they have similar profiles. Use secondary criteria (notional, sector) to differentiate.",
  },
];

/* ─────────────────────────────────────────────────────────────────────────────
   Mental Model Data
   ───────────────────────────────────────────────────────────────────────────── */

const MENTAL_MODEL = {
  gatedVsRanked: {
    title: "Gated vs Ranked",
    icon: Lock,
    gated: ["Universe membership", "Market Regime", "Stock Quality", "Strategy Eligibility", "Options Liquidity"],
    ranked: ["Trade Construction", "Score & Band"],
    summary: "Stages 1–5 are gates (pass/fail). Stages 6–7 rank and prioritize what passed.",
  },
  globalRisk: {
    title: "Global Risk Control",
    icon: Shield,
    description: "Market Regime (Stage 2) is the only global control. It affects ALL symbols equally — caps scores, blocks CSP, removes Band A availability. Per-symbol gates come later.",
  },
  holdDefault: {
    title: "HOLD is the Default",
    icon: AlertTriangle,
    description: "The system is pessimistic by design. Any missing data, liquidity concern, or regime issue defaults to HOLD. ELIGIBLE requires passing every gate explicitly.",
  },
  humanEntry: {
    title: "Human Judgment Entry Points",
    icon: User,
    points: ["Universe selection (what to track)", "Trade execution (whether to act)", "Position sizing (how much)", "Exit timing (when to close)"],
    summary: "The system never executes. It surfaces candidates; you decide.",
  },
};

const RUN_VARIABILITY = {
  changes: [
    { label: "Market Regime", description: "Can shift between RISK_ON, NEUTRAL, RISK_OFF based on index conditions" },
    { label: "Options Liquidity", description: "Bid/ask spreads and OI fluctuate with market activity" },
    { label: "Relative Scores", description: "Same symbol may score differently as peers' data quality changes" },
    { label: "Band Availability", description: "Band A requires RISK_ON — unavailable in NEUTRAL or RISK_OFF" },
  ],
  stable: [
    { label: "Universe", description: "Only changes when you edit config/universe.csv" },
    { label: "Strategy Rules", description: "CSP/CC eligibility logic, delta targets, DTE windows" },
    { label: "Gate Thresholds", description: "What constitutes 'wide spread' or 'thin liquidity'" },
    { label: "Position Awareness", description: "Your open positions determine blocks — data from your journal" },
  ],
};

const COMMON_MISINTERPRETATIONS = [
  {
    myth: "Band C means it's a bad stock",
    reality: "Band C means the system has lower conviction for THIS run — often due to regime (NEUTRAL/RISK_OFF) or minor data gaps. The stock itself may be excellent.",
  },
  {
    myth: "HOLD means permanent rejection",
    reality: "HOLD is temporary. The next run may produce ELIGIBLE if data improves, liquidity tightens, or regime shifts. HOLD = 'not now', not 'never'.",
  },
  {
    myth: "ELIGIBLE means I should execute",
    reality: "ELIGIBLE means the system found no disqualifying issues. It's a candidate, not an instruction. You still review strike, premium, and position sizing.",
  },
  {
    myth: "Higher score = higher probability of profit",
    reality: "Score is relative ranking within THIS run, not a probability. Score 85 vs 75 = slightly better setup, not 10% more likely to succeed.",
  },
  {
    myth: "The system is broken if many symbols have the same score",
    reality: "Score clustering is expected. Many symbols share similar data profiles. Use secondary criteria (notional, sector) to differentiate.",
  },
];

/** Voices supported by OpenAI TTS (used for read-aloud). */
const TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] as const;
const TTS_MAX_CHARS = 4000;

/** Build a single script for TTS from strategy content (under TTS_MAX_CHARS). */
function getReadableStrategyScript(): string {
  const parts: string[] = [];
  parts.push(
    "ChakraOps Strategy. Interactive guide to the evaluation pipeline. Understand how decisions are made, why symbols pass or fail, and how to interpret the output."
  );
  parts.push(
    "Important: ELIGIBLE does not mean execute. ChakraOps surfaces candidates, not orders. The system proposes; you decide. Always review the recommended contract and position sizing before execution."
  );
  parts.push("How ChakraOps thinks. Gated vs Ranked: Stages 1 through 5 are pass-fail gates. Stages 6 and 7 rank and prioritize what passed. Global Risk Control: Market Regime is the only global control; it affects all symbols equally. HOLD is the default: the system is pessimistic by design. Human judgment: you decide universe selection, trade execution, position sizing, and exit timing.");
  PIPELINE_STAGES.forEach((s) => {
    parts.push(`Stage ${s.stageNumber}: ${s.title}. ${s.summary}`);
  });
  const script = parts.join(" ");
  return script.length > TTS_MAX_CHARS ? script.slice(0, TTS_MAX_CHARS) : script;
}

/* ─────────────────────────────────────────────────────────────────────────────
   End-to-End Scenarios
   ───────────────────────────────────────────────────────────────────────────── */

interface ScenarioStep {
  stage: string;
  stageNum: number;
  outcome: "PASS" | "WAIVED" | "HOLD" | "BLOCKED" | "N/A";
  detail: string;
}

interface Scenario {
  id: string;
  title: string;
  description: string;
  symbol: string;
  steps: ScenarioStep[];
  finalVerdict: "ELIGIBLE" | "HOLD" | "BLOCKED";
  finalBand: "A" | "B" | "C";
  operatorAction: string;
}

const SCENARIOS: Scenario[] = [
  {
    id: "ideal-csp",
    title: "Ideal CSP Candidate",
    description: "Clean data, favorable regime, strong liquidity — the textbook setup",
    symbol: "MSFT",
    steps: [
      { stage: "Universe", stageNum: 1, outcome: "PASS", detail: "MSFT in universe.csv" },
      { stage: "Market Regime", stageNum: 2, outcome: "PASS", detail: "RISK_ON — SPY above EMA50, RSI 58" },
      { stage: "Stock Quality", stageNum: 3, outcome: "PASS", detail: "Price, bid/ask, volume, IV rank all present" },
      { stage: "Strategy Eligibility", stageNum: 4, outcome: "PASS", detail: "No open CSP, no position conflicts" },
      { stage: "Options Liquidity", stageNum: 5, outcome: "PASS", detail: "Tight spreads ($0.05), high OI (5,000+)" },
      { stage: "Trade Construction", stageNum: 6, outcome: "PASS", detail: "$410 PUT, -0.23 delta, 28 DTE, $3.20 premium" },
      { stage: "Score & Band", stageNum: 7, outcome: "PASS", detail: "Score: 88, Band A" },
    ],
    finalVerdict: "ELIGIBLE",
    finalBand: "A",
    operatorAction: "Review the recommended contract. If premium/risk acceptable, execute at your discretion. Band A suggests full position size.",
  },
  {
    id: "waived-data",
    title: "Data Waived via Options Confirmation",
    description: "Stock-level bid/ask missing, but options liquidity confirms tradeability",
    symbol: "DIS",
    steps: [
      { stage: "Universe", stageNum: 1, outcome: "PASS", detail: "DIS in universe.csv" },
      { stage: "Market Regime", stageNum: 2, outcome: "PASS", detail: "NEUTRAL — SPY near EMA50" },
      { stage: "Stock Quality", stageNum: 3, outcome: "WAIVED", detail: "Price present, bid/ask null — awaiting downstream confirmation" },
      { stage: "Strategy Eligibility", stageNum: 4, outcome: "PASS", detail: "No open positions" },
      { stage: "Options Liquidity", stageNum: 5, outcome: "PASS", detail: "Options chain confirms liquidity — waiver granted" },
      { stage: "Trade Construction", stageNum: 6, outcome: "PASS", detail: "$95 PUT, -0.26 delta, 35 DTE" },
      { stage: "Score & Band", stageNum: 7, outcome: "PASS", detail: "Score: 71, Band B (penalized for waiver)" },
    ],
    finalVerdict: "ELIGIBLE",
    finalBand: "B",
    operatorAction: "Proceed with caution. Band B due to data gap — consider smaller position size. The waiver is logged for audit.",
  },
  {
    id: "early-block",
    title: "Early Block at Stock Quality",
    description: "Missing price data — evaluation stops early",
    symbol: "PRVT",
    steps: [
      { stage: "Universe", stageNum: 1, outcome: "PASS", detail: "PRVT in universe.csv" },
      { stage: "Market Regime", stageNum: 2, outcome: "PASS", detail: "RISK_ON" },
      { stage: "Stock Quality", stageNum: 3, outcome: "BLOCKED", detail: "No price data returned from provider" },
      { stage: "Strategy Eligibility", stageNum: 4, outcome: "N/A", detail: "Not evaluated — prior stage blocked" },
      { stage: "Options Liquidity", stageNum: 5, outcome: "N/A", detail: "Not evaluated" },
      { stage: "Trade Construction", stageNum: 6, outcome: "N/A", detail: "Not evaluated" },
      { stage: "Score & Band", stageNum: 7, outcome: "N/A", detail: "Score: 0, Band C" },
    ],
    finalVerdict: "BLOCKED",
    finalBand: "C",
    operatorAction: "Check data provider configuration for PRVT. Symbol may be delisted, OTC, or incorrectly formatted. Remove from universe if not resolvable.",
  },
  {
    id: "deprioritized-capital",
    title: "Eligible but Deprioritized (Capital Efficiency)",
    description: "Passes all gates but requires disproportionate capital",
    symbol: "COST",
    steps: [
      { stage: "Universe", stageNum: 1, outcome: "PASS", detail: "COST in universe.csv" },
      { stage: "Market Regime", stageNum: 2, outcome: "PASS", detail: "RISK_ON" },
      { stage: "Stock Quality", stageNum: 3, outcome: "PASS", detail: "All data present" },
      { stage: "Strategy Eligibility", stageNum: 4, outcome: "PASS", detail: "No conflicts" },
      { stage: "Options Liquidity", stageNum: 5, outcome: "PASS", detail: "Liquid chain" },
      { stage: "Trade Construction", stageNum: 6, outcome: "PASS", detail: "$900 PUT, -0.24 delta — CSP requires $90,000 cash secured" },
      { stage: "Score & Band", stageNum: 7, outcome: "PASS", detail: "Score: 82, Band B — sorted below lower-notional alternatives" },
    ],
    finalVerdict: "ELIGIBLE",
    finalBand: "B",
    operatorAction: "Eligible, but high-notional. Sorted after similar-score symbols with lower capital requirements. Consider if $90K allocation fits your portfolio.",
  },
  {
    id: "cc-vs-csp",
    title: "CC vs CSP Ambiguity (Position-Aware)",
    description: "Shares held — CC eligible; CSP blocked by existing position",
    symbol: "AAPL",
    steps: [
      { stage: "Universe", stageNum: 1, outcome: "PASS", detail: "AAPL in universe.csv" },
      { stage: "Market Regime", stageNum: 2, outcome: "PASS", detail: "NEUTRAL" },
      { stage: "Stock Quality", stageNum: 3, outcome: "PASS", detail: "All data present" },
      { stage: "Strategy Eligibility", stageNum: 4, outcome: "PASS", detail: "100 shares held → CC eligible. Open CSP exists → new CSP blocked." },
      { stage: "Options Liquidity", stageNum: 5, outcome: "PASS", detail: "Excellent liquidity" },
      { stage: "Trade Construction", stageNum: 6, outcome: "PASS", detail: "CC: $195 CALL, 0.28 delta, 30 DTE" },
      { stage: "Score & Band", stageNum: 7, outcome: "PASS", detail: "Score: 74, Band B" },
    ],
    finalVerdict: "ELIGIBLE",
    finalBand: "B",
    operatorAction: "Only CC is available — CSP blocked due to existing position. If you want CSP exposure, close the current CSP first.",
  },
];

/* ─────────────────────────────────────────────────────────────────────────────
   Tradeoffs & Non-Goals
   ───────────────────────────────────────────────────────────────────────────── */

const NON_GOALS = [
  {
    id: "intraday",
    title: "Intraday Alpha",
    icon: Clock,
    description: "ChakraOps is designed for end-of-day decisions. It does not attempt to time entries within the trading day or capture intraday momentum.",
  },
  {
    id: "earnings",
    title: "Earnings Gambling",
    icon: AlertTriangle,
    description: "The system does not recommend opening positions around earnings for 'binary' plays. Earnings filters exist to avoid, not exploit, event risk.",
  },
  {
    id: "direction",
    title: "Directional Prediction",
    icon: TrendingUp,
    description: "No attempt is made to predict whether a stock will go up or down. The system screens for quality and opportunity, not direction.",
  },
  {
    id: "leverage",
    title: "High Turnover / Leverage",
    icon: Zap,
    description: "Conservative by design. No margin strategies, no frequent rotation. Steady premium income over time, not aggressive compounding.",
  },
];

/* ─────────────────────────────────────────────────────────────────────────────
   Other Data
   ───────────────────────────────────────────────────────────────────────────── */

const STRATEGY_TYPES = [
  {
    id: "csp",
    title: "Cash-Secured Put (CSP)",
    icon: Shield,
    color: "from-emerald-500 to-teal-500",
    description: "Sell a put option with cash reserved to buy the stock if assigned.",
    when: "When you're willing to own the underlying at the strike price.",
    mechanics: [
      "Collect premium upfront",
      "Obligated to buy shares if price < strike at expiry",
      "Max profit = premium received",
      "Max loss = strike price × 100 - premium (if stock goes to $0)",
    ],
    ideal: "Bullish or neutral outlook, want to enter a position at a discount.",
  },
  {
    id: "cc",
    title: "Covered Call (CC)",
    icon: TrendingUp,
    color: "from-blue-500 to-indigo-500",
    description: "Sell a call option against shares you already own.",
    when: "When you hold shares and want to generate income.",
    mechanics: [
      "Collect premium upfront",
      "Obligated to sell shares if price > strike at expiry",
      "Max profit = premium + (strike - cost basis)",
      "Downside = shares decline in value (unrelated to the call)",
    ],
    ideal: "Neutral to slightly bullish, comfortable selling at strike.",
  },
];

const CORE_PRINCIPLES = [
  {
    id: "preservation",
    title: "Capital Preservation",
    icon: Shield,
    description: "The primary goal is not losing money. Conservative gates ensure only quality setups surface.",
  },
  {
    id: "consistency",
    title: "Consistent Income",
    icon: DollarSign,
    description: "Steady premium collection over time. Small, repeatable wins compound better than swinging for fences.",
  },
  {
    id: "no-prediction",
    title: "No Price Prediction",
    icon: HelpCircle,
    description: "The system screens for opportunity and quality, not direction. It doesn't know if a stock will go up or down.",
  },
  {
    id: "eod",
    title: "End-of-Day Strategy",
    icon: Clock,
    description: "Designed for EOD decisions using snapshot data. One evaluation per day is sufficient for this strategy.",
  },
];

/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

function GlassCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-gradient-to-br from-white/5 to-white/[0.02] backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ title, subtitle, badge }: { title: string; subtitle: string; badge?: string }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold text-foreground">{title}</h2>
        {badge && (
          <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-medium text-primary">{badge}</span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Gate Type Badge
   ───────────────────────────────────────────────────────────────────────────── */

function GateTypeBadge({ type }: { type: GateType }) {
  const config = {
    hard: { label: "Hard Gate", color: "bg-red-500/15 text-red-400", icon: XOctagon },
    soft: { label: "Soft Gate", color: "bg-amber-500/15 text-amber-400", icon: AlertTriangle },
    ranking: { label: "Ranking Only", color: "bg-blue-500/15 text-blue-400", icon: Scale },
  };
  const { label, color, icon: Icon } = config[type];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

function FailureEffectBadge({ effect }: { effect: FailureEffect }) {
  const config = {
    BLOCKED: { color: "text-red-400" },
    HOLD: { color: "text-amber-400" },
    DEPRIORITIZED: { color: "text-blue-400" },
    NONE: { color: "text-muted-foreground" },
  };
  return <span className={`text-xs font-semibold ${config[effect].color}`}>→ {effect}</span>;
}

/* ─────────────────────────────────────────────────────────────────────────────
   Pipeline Node (with visible stage number)
   ───────────────────────────────────────────────────────────────────────────── */

interface PipelineNodeProps {
  stage: StageDetail;
  index: number;
  isSelected: boolean;
  onClick: () => void;
}

function PipelineNode({ stage, index, isSelected, onClick }: PipelineNodeProps) {
  const Icon = stage.icon;
  return (
    <motion.button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col items-center"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.98 }}
    >
      <div className={`absolute -inset-2 rounded-2xl bg-gradient-to-r ${stage.color} opacity-0 blur-xl transition-opacity duration-300 group-hover:opacity-30 ${isSelected ? "opacity-50" : ""}`} />
      <div className={`relative flex h-16 w-16 items-center justify-center rounded-2xl border-2 transition-all duration-300 ${
        isSelected
          ? `border-transparent bg-gradient-to-br ${stage.color} shadow-lg shadow-primary/20`
          : "border-border bg-card hover:border-primary/50"
      }`}>
        <Icon className={`h-7 w-7 ${isSelected ? "text-white" : "text-muted-foreground group-hover:text-foreground"}`} />
        {/* Stage number badge */}
        <span className={`absolute -top-1.5 -left-1.5 flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
          isSelected ? "bg-white text-slate-900" : "bg-primary text-white"
        }`}>
          {stage.stageNumber}
        </span>
      </div>
      <span className={`mt-2 text-xs font-medium transition-colors ${isSelected ? "text-foreground" : "text-muted-foreground"}`}>
        {stage.title}
      </span>
    </motion.button>
  );
}

function PipelineConnector({ index }: { index: number }) {
  return (
    <motion.div
      className="flex items-center px-2"
      initial={{ opacity: 0, scaleX: 0 }}
      animate={{ opacity: 1, scaleX: 1 }}
      transition={{ delay: index * 0.08 + 0.15, duration: 0.3 }}
    >
      <div className="h-[2px] w-8 bg-gradient-to-r from-border to-muted-foreground/40" />
      <ArrowRight className="h-4 w-4 text-muted-foreground/60" />
    </motion.div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Stage Detail Panel (wider — 75% width, stronger backdrop)
   ───────────────────────────────────────────────────────────────────────────── */

interface StageDetailPanelProps {
  stage: StageDetail | null;
  onClose: () => void;
}

function StageDetailPanel({ stage, onClose }: StageDetailPanelProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["decision"]));

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
  };

  if (!stage) return null;
  const Icon = stage.icon;

  const sections = [
    { id: "decision", title: "Decision Lens", icon: Eye, highlight: true },
    { id: "purpose", title: "Why It Exists", icon: Lightbulb },
    { id: "inputs", title: "Inputs", icon: ArrowRight },
    { id: "outputs", title: "Outputs", icon: CheckCircle2 },
    { id: "failures", title: "Failure Modes", icon: AlertTriangle },
    { id: "example", title: "Example", icon: BookOpen },
  ];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={stage.id}
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -20, scale: 0.98 }}
        transition={{ duration: 0.3 }}
        className="mt-8"
      >
        <div className="overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.07] to-white/[0.02] backdrop-blur-md shadow-2xl">
          {/* Header with stage number */}
          <div className={`bg-gradient-to-r ${stage.color} p-6`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="relative flex h-16 w-16 items-center justify-center rounded-xl bg-white/20 backdrop-blur-sm">
                  <Icon className="h-8 w-8 text-white" />
                  <span className="absolute -top-2 -left-2 flex h-7 w-7 items-center justify-center rounded-full bg-white text-sm font-bold text-slate-900">
                    {stage.stageNumber}
                  </span>
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-white">Stage {stage.stageNumber}: {stage.title}</h3>
                  <p className="mt-0.5 text-sm text-white/80">{stage.summary}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-2 text-white/70 hover:bg-white/10 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="divide-y divide-border">
            {sections.map((section) => {
              const isExpanded = expandedSections.has(section.id);
              const SectionIcon = section.icon;

              return (
                <div key={section.id} className={section.highlight ? "bg-primary/5" : ""}>
                  <button
                    type="button"
                    onClick={() => toggleSection(section.id)}
                    className={`flex w-full items-center justify-between p-4 text-left transition-colors ${section.highlight ? "hover:bg-primary/10" : "hover:bg-muted/30"}`}
                  >
                    <div className="flex items-center gap-3">
                      <SectionIcon className={`h-4 w-4 ${section.highlight ? "text-primary" : "text-muted-foreground"}`} />
                      <span className={`text-sm font-medium ${section.highlight ? "text-primary" : "text-foreground"}`}>{section.title}</span>
                      {section.highlight && <span className="rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-semibold text-primary">KEY</span>}
                    </div>
                    <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    </motion.div>
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-4 pb-4 pl-11">
                          {section.id === "decision" ? (
                            <div className="space-y-3">
                              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
                                <p className="text-sm font-medium text-foreground">{stage.decisionLens.decision}</p>
                              </div>
                              <div className="flex flex-wrap items-center gap-3">
                                <GateTypeBadge type={stage.decisionLens.gateType} />
                                <FailureEffectBadge effect={stage.decisionLens.failureEffect} />
                              </div>
                              <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3">
                                <User className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                                <p className="text-sm text-foreground">{stage.decisionLens.operatorTakeaway}</p>
                              </div>
                            </div>
                          ) : section.id === "inputs" || section.id === "outputs" ? (
                            <ul className="space-y-1.5">
                              {(section.id === "inputs" ? stage.inputs : stage.outputs).map((item, i) => (
                                <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                          ) : section.id === "failures" ? (
                            <div className="space-y-2">
                              {stage.failureModes.map((f, i) => (
                                <div key={i} className="rounded-lg bg-destructive/10 p-3">
                                  <p className="text-sm font-medium text-destructive">{f.condition}</p>
                                  <p className="mt-1 text-sm text-muted-foreground">→ {f.result}</p>
                                </div>
                              ))}
                            </div>
                          ) : section.id === "example" ? (
                            <div className="rounded-lg bg-primary/10 p-3">
                              <p className="text-sm text-foreground">{stage.example.scenario}</p>
                              <p className="mt-2 text-sm font-medium text-primary">→ {stage.example.outcome}</p>
                            </div>
                          ) : (
                            <p className="text-sm leading-relaxed text-muted-foreground">{stage.purpose}</p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>

          {/* Tip */}
          <div className="flex items-start gap-3 border-t border-border bg-muted/30 p-4">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <p className="text-sm leading-relaxed text-muted-foreground">{stage.tip}</p>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Scenario Card
   ───────────────────────────────────────────────────────────────────────────── */

interface ScenarioCardProps {
  scenario: Scenario;
  isExpanded: boolean;
  onToggle: () => void;
}

function ScenarioCard({ scenario, isExpanded, onToggle }: ScenarioCardProps) {
  const verdictColors = {
    ELIGIBLE: "bg-emerald-500",
    HOLD: "bg-amber-500",
    BLOCKED: "bg-red-500",
  };
  const bandColors = { A: "bg-emerald-500", B: "bg-amber-500", C: "bg-slate-500" };
  const outcomeColors = {
    PASS: "text-emerald-400",
    WAIVED: "text-amber-400",
    HOLD: "text-amber-400",
    BLOCKED: "text-red-400",
    "N/A": "text-muted-foreground",
  };

  return (
    <GlassCard className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted">
            <Play className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-medium text-foreground">{scenario.title}</h4>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold text-white ${verdictColors[scenario.finalVerdict]}`}>
                {scenario.finalVerdict}
              </span>
              <span className={`flex h-4 w-4 items-center justify-center rounded text-[10px] font-bold text-white ${bandColors[scenario.finalBand]}`}>
                {scenario.finalBand}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">{scenario.description}</p>
          </div>
        </div>
        <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown className="h-5 w-5 text-muted-foreground" />
        </motion.div>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="border-t border-border p-4 space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Symbol:</span>
                <span className="font-mono text-sm font-semibold text-foreground">{scenario.symbol}</span>
              </div>

              <div className="space-y-2">
                {scenario.steps.map((step, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg bg-muted/30 p-3">
                    <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                      step.outcome === "PASS" || step.outcome === "WAIVED" ? "bg-primary text-white" :
                      step.outcome === "N/A" ? "bg-muted text-muted-foreground" : "bg-destructive/80 text-white"
                    }`}>
                      {step.stageNum}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">{step.stage}</span>
                        <span className={`text-xs font-semibold ${outcomeColors[step.outcome]}`}>{step.outcome}</span>
                      </div>
                      <p className="mt-0.5 text-sm text-muted-foreground">{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
                  <User className="h-3.5 w-3.5" />
                  Operator Action
                </div>
                <p className="mt-1.5 text-sm text-foreground">{scenario.operatorAction}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Strategy Type Card
   ───────────────────────────────────────────────────────────────────────────── */

interface StrategyTypeCardProps {
  strategy: typeof STRATEGY_TYPES[0];
  isExpanded: boolean;
  onToggle: () => void;
}

function StrategyTypeCard({ strategy, isExpanded, onToggle }: StrategyTypeCardProps) {
  const Icon = strategy.icon;
  return (
    <GlassCard className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${strategy.color}`}>
            <Icon className="h-5 w-5 text-white" />
          </div>
          <div>
            <h4 className="font-medium text-foreground">{strategy.title}</h4>
            <p className="text-sm text-muted-foreground">{strategy.description}</p>
          </div>
        </div>
        <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown className="h-5 w-5 text-muted-foreground" />
        </motion.div>
      </button>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-4 border-t border-border p-4">
              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">When to use</h5>
                <p className="mt-1 text-sm text-foreground">{strategy.when}</p>
              </div>
              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Mechanics</h5>
                <ul className="mt-2 space-y-1.5">
                  {strategy.mechanics.map((m, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      {m}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-lg bg-primary/10 p-3">
                <p className="text-sm text-foreground"><strong>Ideal for:</strong> {strategy.ideal}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Principle Card
   ───────────────────────────────────────────────────────────────────────────── */

function PrincipleCard({ principle, index }: { principle: typeof CORE_PRINCIPLES[0]; index: number }) {
  const Icon = principle.icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
    >
      <GlassCard className="h-full p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <h4 className="mt-3 font-medium text-foreground">{principle.title}</h4>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{principle.description}</p>
      </GlassCard>
    </motion.div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Non-Goal Card
   ───────────────────────────────────────────────────────────────────────────── */

function NonGoalCard({ item, index }: { item: typeof NON_GOALS[0]; index: number }) {
  const Icon = item.icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
      className="flex items-start gap-3 rounded-xl border border-border/50 bg-muted/20 p-4"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-destructive/15">
        <Icon className="h-4 w-4 text-destructive" />
      </div>
      <div>
        <h4 className="font-medium text-foreground">{item.title}</h4>
        <p className="mt-0.5 text-sm text-muted-foreground">{item.description}</p>
      </div>
    </motion.div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Common Misinterpretations Card
   ───────────────────────────────────────────────────────────────────────────── */

function MisinterpretationCard({ item, index }: { item: typeof COMMON_MISINTERPRETATIONS[0]; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="rounded-lg border border-border bg-muted/20 p-4"
    >
      <div className="flex items-start gap-2">
        <Ban className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <p className="text-sm font-medium text-destructive">{item.myth}</p>
      </div>
      <div className="mt-2 flex items-start gap-2 pl-6">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
        <p className="text-sm text-muted-foreground">{item.reality}</p>
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════════════════════ */

export function StrategyPage() {
  const [selectedStage, setSelectedStage] = useState<StageDetail | null>(null);
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);
  const [showMisinterpretations, setShowMisinterpretations] = useState(false);
  const [ttsStatus, setTtsStatus] = useState<"idle" | "loading" | "playing">("idle");
  const [ttsError, setTtsError] = useState<string | null>(null);
  const [ttsVoice, setTtsVoice] = useState<string>("nova");
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);

  const handleStageClick = useCallback((stage: StageDetail) => {
    setSelectedStage((prev) => (prev?.id === stage.id ? null : stage));
  }, []);

  const handleTtsPlay = useCallback(async () => {
    if (ttsStatus === "playing" && ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current = null;
      setTtsStatus("idle");
      return;
    }
    setTtsError(null);
    setTtsStatus("loading");
    const text = getReadableStrategyScript();
    const url = getResolvedUrl(ENDPOINTS.ttsSpeech);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: ttsVoice }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = (err as { detail?: string }).detail;
        if (detail) throw new Error(detail);
        if (res.status === 502) {
          throw new Error(
            "TTS failed. Start the backend (e.g. cd chakraops && python -m uvicorn app.api.server:app --port 8000) and set OPENAI_API_KEY in chakraops/.env."
          );
        }
        throw new Error(res.statusText || "TTS failed");
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const audio = new Audio(blobUrl);
      ttsAudioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(blobUrl);
        ttsAudioRef.current = null;
        setTtsStatus("idle");
      };
      audio.onerror = () => {
        URL.revokeObjectURL(blobUrl);
        ttsAudioRef.current = null;
        setTtsStatus("idle");
        setTtsError("Playback failed");
      };
      await audio.play();
      setTtsStatus("playing");
    } catch (e) {
      setTtsStatus("idle");
      setTtsError(e instanceof Error ? e.message : "TTS failed");
    }
  }, [ttsStatus, ttsVoice]);

  return (
    <div className="min-h-screen">
      {/* Hero — full width */}
      <div className="relative overflow-hidden border-b border-border bg-gradient-to-b from-primary/5 to-transparent px-4 py-12 sm:px-6 lg:px-8">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent" />
        <div className="relative mx-auto max-w-7xl text-center">
          <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
            <h1 className="text-3xl font-bold text-foreground sm:text-4xl">ChakraOps Strategy</h1>
            <p className="mx-auto mt-3 max-w-3xl text-base text-muted-foreground">
              Interactive guide to the evaluation pipeline. Understand how decisions are made,
              why symbols pass or fail, and how to interpret the output.
            </p>
            {/* Read-aloud (OpenAI TTS via backend) */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Voice:</span>
                <select
                  value={ttsVoice}
                  onChange={(e) => setTtsVoice(e.target.value)}
                  disabled={ttsStatus === "loading"}
                  className="rounded-md border border-border bg-background px-2 py-1 text-foreground"
                >
                  {TTS_VOICES.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handleTtsPlay}
                disabled={ttsStatus === "loading"}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              >
                {ttsStatus === "loading" ? (
                  <>Loading…</>
                ) : ttsStatus === "playing" ? (
                  <>
                    <Square className="h-4 w-4" /> Stop
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" /> Listen to overview
                  </>
                )}
              </button>
              {ttsError && (
                <span className="text-sm text-destructive">{ttsError}</span>
              )}
            </div>
          </motion.div>
        </div>
      </div>

      {/* Content — wider container */}
      <div className="mx-auto max-w-7xl space-y-14 px-4 py-10 sm:px-6 lg:px-8">
        {/* Critical Guardrail */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
        >
          <GlassCard className="border-amber-500/30 bg-gradient-to-br from-amber-500/10 to-transparent p-5">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-500/20">
                <AlertTriangle className="h-6 w-6 text-amber-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-foreground">ELIGIBLE ≠ EXECUTE</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  ChakraOps surfaces <strong>candidates</strong>, not orders. An ELIGIBLE verdict means the symbol passed all quality and liquidity gates — it does <em>not</em> mean you should trade it automatically. The system proposes; you decide. Always review the recommended contract, verify it fits your risk tolerance, and confirm position sizing before execution.
                </p>
              </div>
            </div>
          </GlassCard>
        </motion.section>

        {/* How ChakraOps Thinks — Mental Model (1 minute) */}
        <section>
          <SectionHeader
            title="How ChakraOps Thinks"
            subtitle="1-minute mental model — understand the system's decision architecture"
            badge="Start Here"
          />
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Gated vs Ranked */}
            <GlassCard className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15">
                  <Lock className="h-5 w-5 text-primary" />
                </div>
                <h4 className="font-semibold text-foreground">{MENTAL_MODEL.gatedVsRanked.title}</h4>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-red-500/10 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-red-400">
                    <XOctagon className="h-3.5 w-3.5" /> Gated (Pass/Fail)
                  </div>
                  <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                    {MENTAL_MODEL.gatedVsRanked.gated.map((g, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="flex h-4 w-4 items-center justify-center rounded bg-muted text-[10px] font-bold text-muted-foreground">{i + 1}</span>
                        {g}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-lg bg-blue-500/10 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-400">
                    <Scale className="h-3.5 w-3.5" /> Ranked (Prioritize)
                  </div>
                  <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                    {MENTAL_MODEL.gatedVsRanked.ranked.map((r, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="flex h-4 w-4 items-center justify-center rounded bg-muted text-[10px] font-bold text-muted-foreground">{i + 6}</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">{MENTAL_MODEL.gatedVsRanked.summary}</p>
            </GlassCard>

            {/* Global Risk Control */}
            <GlassCard className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/15">
                  <Shield className="h-5 w-5 text-violet-400" />
                </div>
                <h4 className="font-semibold text-foreground">{MENTAL_MODEL.globalRisk.title}</h4>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{MENTAL_MODEL.globalRisk.description}</p>
              <div className="mt-4 flex items-center gap-2 rounded-lg bg-violet-500/10 p-3">
                <Activity className="h-4 w-4 text-violet-400" />
                <span className="text-sm font-medium text-violet-300">Stage 2: Market Regime is the global switch</span>
              </div>
            </GlassCard>

            {/* HOLD is Default */}
            <GlassCard className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/15">
                  <AlertTriangle className="h-5 w-5 text-amber-400" />
                </div>
                <h4 className="font-semibold text-foreground">{MENTAL_MODEL.holdDefault.title}</h4>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{MENTAL_MODEL.holdDefault.description}</p>
              <div className="mt-4 rounded-lg bg-amber-500/10 p-3">
                <p className="text-sm text-amber-300">
                  <strong>Implication:</strong> Seeing many HOLDs is normal — the system is being conservative.
                </p>
              </div>
            </GlassCard>

            {/* Human Judgment Entry */}
            <GlassCard className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15">
                  <User className="h-5 w-5 text-emerald-400" />
                </div>
                <h4 className="font-semibold text-foreground">{MENTAL_MODEL.humanEntry.title}</h4>
              </div>
              <ul className="mt-3 space-y-1.5">
                {MENTAL_MODEL.humanEntry.points.map((p, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Unlock className="h-3.5 w-3.5 text-emerald-400" />
                    {p}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm font-medium text-emerald-300">{MENTAL_MODEL.humanEntry.summary}</p>
            </GlassCard>
          </div>
        </section>

        {/* Core Principles */}
        <section>
          <SectionHeader title="Core Principles" subtitle="The philosophy behind every decision" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {CORE_PRINCIPLES.map((principle, i) => (
              <PrincipleCard key={principle.id} principle={principle} index={i} />
            ))}
          </div>
        </section>

        {/* Pipeline Flow */}
        <section>
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-semibold text-foreground">Evaluation Pipeline</h2>
                <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-medium text-primary">Interactive</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">7 stages — click any to explore. Symbols flow left to right.</p>
            </div>
            <Link
              to="/pipeline"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm font-medium text-foreground hover:bg-muted"
            >
              Pipeline Details (implementation reference)
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <GlassCard className="p-6 lg:p-8">
            <div className="overflow-x-auto pb-2">
              <div className="flex min-w-max items-center justify-center gap-0">
                {PIPELINE_STAGES.map((stage, index) => (
                  <div key={stage.id} className="flex items-center">
                    <PipelineNode
                      stage={stage}
                      index={index}
                      isSelected={selectedStage?.id === stage.id}
                      onClick={() => handleStageClick(stage)}
                    />
                    {index < PIPELINE_STAGES.length - 1 && <PipelineConnector index={index} />}
                  </div>
                ))}
              </div>
            </div>
            <AnimatePresence mode="wait">
              {selectedStage && <StageDetailPanel stage={selectedStage} onClose={() => setSelectedStage(null)} />}
            </AnimatePresence>
          </GlassCard>
        </section>

        {/* What Changes From Run to Run */}
        <section>
          <SectionHeader
            title="What Changes From Run to Run"
            subtitle="Some inputs are dynamic; others are fixed by you"
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <GlassCard className="p-5">
              <div className="flex items-center gap-3 text-amber-400">
                <RefreshCw className="h-5 w-5" />
                <h4 className="font-semibold text-foreground">Can Change Between Runs</h4>
              </div>
              <ul className="mt-4 space-y-3">
                {RUN_VARIABILITY.changes.map((item, i) => (
                  <li key={i} className="rounded-lg bg-amber-500/10 p-3">
                    <p className="text-sm font-medium text-foreground">{item.label}</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">{item.description}</p>
                  </li>
                ))}
              </ul>
            </GlassCard>
            <GlassCard className="p-5">
              <div className="flex items-center gap-3 text-emerald-400">
                <Lock className="h-5 w-5" />
                <h4 className="font-semibold text-foreground">Stable (Operator-Controlled)</h4>
              </div>
              <ul className="mt-4 space-y-3">
                {RUN_VARIABILITY.stable.map((item, i) => (
                  <li key={i} className="rounded-lg bg-emerald-500/10 p-3">
                    <p className="text-sm font-medium text-foreground">{item.label}</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">{item.description}</p>
                  </li>
                ))}
              </ul>
            </GlassCard>
          </div>
        </section>

        {/* Score & Band Deep Dive */}
        <section>
          <SectionHeader
            title="Understanding Score & Band"
            subtitle="What the numbers mean — and what they don't"
          />
          <GlassCard className="p-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-4">
                <h4 className="flex items-center gap-2 font-semibold text-foreground">
                  <Gauge className="h-5 w-5 text-primary" />
                  Score (0–100)
                </h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span><strong>Relative ranking</strong> within the current run — not an absolute quality measure</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span><strong>Score ≠ probability</strong> — 85 does not mean "85% chance of success"</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span><strong>Scores cluster</strong> because many symbols share similar data profiles. This is expected, not a bug.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span>When scores tie, use secondary criteria (notional, sector, personal conviction) to differentiate</span>
                  </li>
                </ul>
              </div>
              <div className="space-y-4">
                <h4 className="flex items-center gap-2 font-semibold text-foreground">
                  <Scale className="h-5 w-5 text-primary" />
                  Confidence Band (A/B/C)
                </h4>
                <div className="space-y-3">
                  <div className="flex items-start gap-3 rounded-lg bg-emerald-500/10 p-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-emerald-500 text-xs font-bold text-white">A</span>
                    <div>
                      <p className="text-sm font-medium text-foreground">Highest conviction — rare by design</p>
                      <p className="text-xs text-muted-foreground">RISK_ON regime + 100% data + strong liquidity + ELIGIBLE. Suggests full position size.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 rounded-lg bg-amber-500/10 p-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-amber-500 text-xs font-bold text-white">B</span>
                    <div>
                      <p className="text-sm font-medium text-foreground">Moderate conviction</p>
                      <p className="text-xs text-muted-foreground">NEUTRAL regime or minor data gaps (waived). Suggests reduced position size.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 rounded-lg bg-slate-500/10 p-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-slate-500 text-xs font-bold text-white">C</span>
                    <div>
                      <p className="text-sm font-medium text-foreground">Low conviction — default for HOLD/BLOCKED</p>
                      <p className="text-xs text-muted-foreground">Most symbols land here. This is the system being conservative, not broken.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-6 rounded-lg border border-border bg-muted/30 p-4">
              <p className="text-sm text-muted-foreground">
                <strong className="text-foreground">Why Band A/B are rare:</strong> The system is calibrated conservatively. Band A requires RISK_ON (often the market is NEUTRAL or worse), full data completeness (many symbols have gaps), and strong liquidity. This combination is uncommon — and that's intentional. When you see Band A, it means all conditions aligned.
              </p>
            </div>
          </GlassCard>
        </section>

        {/* End-to-End Scenarios */}
        <section>
          <SectionHeader
            title="End-to-End Scenarios"
            subtitle="See how symbols flow through the pipeline in different situations"
            badge="5 examples"
          />
          <div className="space-y-3">
            {SCENARIOS.map((scenario) => (
              <ScenarioCard
                key={scenario.id}
                scenario={scenario}
                isExpanded={expandedScenario === scenario.id}
                onToggle={() => setExpandedScenario((prev) => (prev === scenario.id ? null : scenario.id))}
              />
            ))}
          </div>
        </section>

        {/* Strategy Types */}
        <section>
          <SectionHeader title="Supported Strategies" subtitle="The two income strategies ChakraOps evaluates" />
          <div className="grid gap-4 md:grid-cols-2">
            {STRATEGY_TYPES.map((strategy) => (
              <StrategyTypeCard
                key={strategy.id}
                strategy={strategy}
                isExpanded={expandedStrategy === strategy.id}
                onToggle={() => setExpandedStrategy((prev) => (prev === strategy.id ? null : strategy.id))}
              />
            ))}
          </div>
        </section>

        {/* Tradeoffs & Non-Goals */}
        <section>
          <SectionHeader
            title="Tradeoffs & Non-Goals"
            subtitle="What ChakraOps explicitly does NOT optimize for"
          />
          <div className="grid gap-3 sm:grid-cols-2">
            {NON_GOALS.map((item, i) => (
              <NonGoalCard key={item.id} item={item} index={i} />
            ))}
          </div>
        </section>

        {/* Common Misinterpretations (collapsed) */}
        <section>
          <GlassCard className="overflow-hidden">
            <button
              type="button"
              onClick={() => setShowMisinterpretations((v) => !v)}
              className="flex w-full items-center justify-between p-5 text-left hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-destructive/15">
                  <MessageCircleWarning className="h-5 w-5 text-destructive" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">Common Misinterpretations</h3>
                  <p className="text-sm text-muted-foreground">What the system output does NOT mean</p>
                </div>
              </div>
              <motion.div animate={{ rotate: showMisinterpretations ? 180 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronDown className="h-5 w-5 text-muted-foreground" />
              </motion.div>
            </button>
            <AnimatePresence>
              {showMisinterpretations && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <div className="border-t border-border p-5 space-y-3">
                    {COMMON_MISINTERPRETATIONS.map((item, i) => (
                      <MisinterpretationCard key={i} item={item} index={i} />
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </GlassCard>
        </section>

        {/* Quick Reference */}
        <section>
          <SectionHeader title="Quick Reference" subtitle="Verdict definitions at a glance" />
          <GlassCard className="p-6">
            <div className="grid gap-6 sm:grid-cols-3">
              <div>
                <h4 className="flex items-center gap-2 font-medium text-foreground">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  ELIGIBLE
                </h4>
                <p className="mt-1 text-sm text-muted-foreground">
                  Passed all gates. A <em>candidate</em> for trading — requires human review before execution.
                </p>
              </div>
              <div>
                <h4 className="flex items-center gap-2 font-medium text-foreground">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  HOLD
                </h4>
                <p className="mt-1 text-sm text-muted-foreground">
                  Failed a soft gate (data, liquidity, regime). No recommendation now, but not permanently blocked.
                </p>
              </div>
              <div>
                <h4 className="flex items-center gap-2 font-medium text-foreground">
                  <Ban className="h-4 w-4 text-red-500" />
                  BLOCKED
                </h4>
                <p className="mt-1 text-sm text-muted-foreground">
                  Failed a hard gate (no price, position conflict). Cannot proceed through this pipeline run.
                </p>
              </div>
            </div>
          </GlassCard>
        </section>
      </div>
    </div>
  );
}

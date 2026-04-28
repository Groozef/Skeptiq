# Skeptiq — Signals Journal

Manual log of every Telegram-sent signal. Used as a paper-trading record and as
retrospective material for confidence-formula calibration once we have ≥30
closed signals.

## Schema (per entry)

- **Sent** — UTC and trader-local timestamp
- **Source / URL / title** — news item that triggered the signal
- **Entry** — `price_at_send` (Binance close at moment of fire)
- **Tech** — RSI(14) / above-EMA20 / volume spike / 24h change at entry
- **Tech alignment** — confirms / neutral / contradicts (per Skeptiq logic)
- **Raw confidence** — what the LLM said
- **Calibrated confidence** — after alignment + RSI penalties
- **Impact / Horizon** — LLM call
- **SL / TP** — invalidation-derived stop, 1:2 R:R take-profit
- **Manual review (Claude)** — discretionary trader read of the signal as
  a sanity check on the LLM's call
- **Outcome** — filled in over time at +1h / +6h / +24h, plus final
  hit-or-miss verdict

---

## #001 — BTC SHORT

**Status:** OPEN (bot stopped manually after one cycle)

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 13:59:21 |
| Sent (Asia/Almaty) | 2026-04-28 18:59 |
| Source | cointelegraph |
| Title | Bitcoin ETFs snap nine-day inflow run as BTC slips below $77K |
| URL | https://cointelegraph.com/news/bitcoin-etf-end-nine-day-inflow-streak-btc-77k |
| Entry | $76,182.01 |
| RSI(14) | 32.3 (near-oversold) |
| Above EMA20 | ❌ |
| Volume spike | ✅ 2.34× avg |
| 24h change | −2.01% |
| Tech alignment | neutral |
| Raw confidence | 0.62 |
| **v0.2 calibrated** | **0.44** ⚠️ would not have fired under v0.2 |
| Impact / Horizon | medium / hours |
| SL (retroactive est.) | ~$77,000 (atr_2_5x) |
| TP (retroactive est.) | ~$74,500 (1:2 R:R) |

### LLM thesis
US spot Bitcoin ETFs reported $263M net outflows, snapping a 9-day consecutive
inflow streak. BTC simultaneously failed to reclaim $80K and slipped below $77K.

### Manual review (Claude as discretionary trader)

**What I like:**
- Counter-signals the LLM listed are concrete and credible:
  outflow-break-resumption pattern, $263M not extreme historically,
  macro/equity-dependent reversal risk, end-of-streak normalization.
- Volume spike + bearish news is technically a real bearish confirmation.

**What I don't:**
1. **RSI 32.3 + volume spike + below EMA20** is a textbook *selling-climax*
   pattern, not a continuation. Going short into RSI ~30 with a volume
   surge is fading the immediate technical reflex.
2. **Horizon mismatch.** ETF flow data publishes with a 1-day lag and is
   typically priced over 1–3 days, not in hours. A "hours" horizon on a
   daily driver is internally inconsistent.
3. **No confluence.** Only one independent signal layer (news). No
   funding-rate read, no macro context. 0.62 with one layer is overstated.

**Verdict:** **SKIP.** Realistic edge ~50–53%, not 62%. v0.2 calibrated
correctly to 0.44 (would have been filtered out). This is the canonical
example of the "raw LLM confidence is overstated for one-layer signals"
problem.

### Outcome (track over time)

| Mark | Price | PnL for short | Notes |
|---|---|---|---|
| +1h (~15:00 UTC) | $75,929.26 | +0.33% | ✅ direction correct, noise-range |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($74,500)? | PENDING | — | — |
| SL hit ($77,000)? | PENDING | — | — |
| Final verdict | PENDING | — | — |

---

## #002 — ETH LONG

**Status:** OPEN (bot stopped manually after one cycle)

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 14:01:51 |
| Sent (Asia/Almaty) | 2026-04-28 19:01 |
| Source | cointelegraph |
| Title | Acting AG Todd Blanche confirms "code is not a crime" in DOJ pivot |
| URL | https://cointelegraph.com/news/acting-ag-blanche-signals-doj-pivot-code-is-not-a-crime |
| Entry | $2,272.78 |
| RSI(14) | 35.3 (low-neutral) |
| Above EMA20 | ❌ |
| Volume spike | ❌ (volume_ratio 0.02 — extremely low; possibly Binance kline anomaly at the time of fetch) |
| 24h change | −1.81% |
| Tech alignment | confirms (RSI<50 + below EMA20 → "room to run" interpretation) |
| Raw confidence | 0.62 |
| **v0.2 calibrated** | **0.67** (alignment confirms +0.05) — would have fired |
| Impact / Horizon | high / **days** |
| SL (retroactive est.) | ~$2,222 (atr_2_5x) |
| TP (retroactive est.) | ~$2,373 (1:2 R:R) |
| LLM affected_tickers | ETH, XMR, TORN |

### LLM thesis
Acting US Attorney General Todd Blanche announced a DOJ policy shift: writing
code is not a crime; developers will not be charged unless they knowingly
assist third parties in committing crimes. Removes a structural overhang for
DeFi / privacy / open-source crypto development.

### Manual review (Claude as discretionary trader)

**What I like:**
- This is a **structural** change (regulatory posture), not a noise event. The
  LLM correctly tagged horizon=`days` and impact=`high`.
- Affected tickers list is exactly right: ETH (DeFi infra), XMR (privacy),
  TORN (the literal protocol that was prosecuted). Watchlist intersection
  catches ETH cleanly.
- LLM counter-signals are sharp: acting AG (not confirmed), Roman Storm case
  still active, OFAC sanctions still in place — all true and material
  caveats.

**What I don't / what's missing:**
1. **Volume_ratio 0.02 looks broken.** Average volume should be much higher
   for ETH at any moment. Likely a Binance API quirk on that specific window
   or a calculation issue when the candle closed seconds before fetch. Worth
   a code-side investigation.
2. **Tech alignment "confirms" because RSI<50 + below EMA20 is the v0.1
   "room to run" rule.** That's a contrarian read. For a *days*-horizon
   structural news event, the more relevant tech check would be: does this
   level historically hold as support? Skeptiq doesn't yet do
   structural-level analysis.
3. **No macro check.** If SPX is dumping or DXY is ripping, regulatory good
   news for ETH gets overridden by macro risk-off. We don't read that yet.
4. **No funding/OI data.** Knowing ETH funding rate and OI would tell us
   whether longs are already crowded ahead of this news.

**Verdict:** **TAKE with reduced size.** The thesis is real and the horizon
is appropriate for a positional trade (days, not minutes). But I'd cut the
position to 50% normal size because we don't yet have macro confirmation,
and a "days" horizon means a real possibility of macro headwinds catching up
mid-trade. Calibrated 0.67 feels roughly right for a single-layer
high-impact news event.

### Outcome (track over time)

| Mark | Price | PnL for long | Notes |
|---|---|---|---|
| +1h | NO DATA YET | — | (only ~1h since send) |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| +days (best window for this signal) | PENDING | — | — |
| TP hit ($2,373)? | PENDING | — | — |
| SL hit ($2,222)? | PENDING | — | — |
| Final verdict | PENDING | — | — |

Current spot snapshot at +1.1h: ETH = $2,271.97 (−0.04%, basically flat).

---

## Template for new signals

When a new signal fires, append:

```
## #NNN — TICKER DIRECTION

**Status:** OPEN

| Field | Value |
| Sent (UTC) | YYYY-MM-DD HH:MM |
| Source / URL / Title | ... |
| Entry | $X |
| Tech (RSI / EMA / vol / 24h) | ... |
| Alignment | confirms/neutral/contradicts |
| Raw / Calibrated confidence | X.XX → Y.YY |
| Impact / Horizon | ... |
| SL / TP | $X / $Y |

### LLM thesis
(copy summary)

### Manual review (Claude as trader)
- What I like
- What I don't
- Verdict: TAKE / TAKE-REDUCED / SKIP

### Outcome
(track at +1h / +6h / +24h / final)
```

---

## Aggregate stats (rolling)

Will be filled once we have ≥10 closed signals.

| Metric | Value |
|---|---|
| Closed signals | 0 |
| Wins (TP hit) | — |
| Losses (SL hit) | — |
| Win rate | — |
| Avg R achieved | — |
| Realized EV per signal (R) | — |

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

## #003 — AAVE LONG
<!-- skeptiq:db_id=3 sent_at=2026-04-28T15:44:10.220294 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:44:10 |
| Source | decrypt |
| Title | Aave-Led 'DeFi United' Relief Effort Raises $300 Million to Cover Kelp DAO Exploit Losses |
| URL | https://decrypt.co/365724/aave-led-defi-united-relief-effort-raises-300m-kelp-dao-losses |
| Entry | $96.20 |
| RSI(14) | 44.2 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.54% |
| Tech alignment | confirms |
| Confidence | 0.60 (base 0.55) |
| Impact / Horizon | high / days |
| SL / TP | $95.24 / $98.12 |
| Invalidation kind | swing_low |

### LLM thesis
An Aave-led cross-protocol initiative dubbed "DeFi United" has reportedly raised $300 million in commitments to cover losses stemming from an exploit targeting Kelp DAO, fully replenishing the affected funds.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=003 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($98.12)? | PENDING | — | — |
| SL hit ($95.24)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #004 — AAVE SHORT
<!-- skeptiq:db_id=4 sent_at=2026-04-28T15:50:00.250000 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:50:00 |
| Source | cointelegraph |
| Title | Aave-linked DeFi United unveils rsETH recovery plan after $293M Kelp exploit |
| URL | https://cointelegraph.com/news/aave-linked-defi-united-outlines-plan-to-restore-rseth-backing-after-293m-exploit?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound |
| Entry | $96.20 |
| RSI(14) | 44.2 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.54% |
| Tech alignment | confirms |
| Confidence | 0.67 (base 0.62) |
| Impact / Horizon | high / days |
| SL / TP | $98.86 / $90.88 |
| Invalidation kind | swing_high |

### LLM thesis
DeFi United, linked to Aave, has published a technical recovery plan to restore the backing of rsETH and unwind DeFi positions connected to the attacker following a reported $293 million exploit of the Kelp protocol. The plan is in response to an exploit that has already occurred, not a prospective event.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=004 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($90.88)? | PENDING | — | — |
| SL hit ($98.86)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #005 — BTC LONG
<!-- skeptiq:db_id=5 sent_at=2026-04-28T15:52:56.008829 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:52:56 |
| Source | coindesk |
| Title | Jack Dorsey's Block nears 9,000 bitcoin in treasury after Q1 addition |
| URL | https://www.coindesk.com/business/2026/04/28/jack-dorsey-s-block-nears-9-000-bitcoin-in-treasury-after-q1-addition |
| Entry | $75,949.99 |
| RSI(14) | 29.0 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.40% |
| Tech alignment | confirms |
| Confidence | 0.60 (base 0.55) |
| Impact / Horizon | medium / days |
| SL / TP | $75,666.60 / $76,516.77 |
| Invalidation kind | swing_low |

### LLM thesis
Jack Dorsey's Block Inc. has grown its Bitcoin treasury to nearly 9,000 BTC following a first-quarter 2026 addition to its holdings. The announcement confirms continued accumulation by a publicly traded crypto-adjacent company.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=005 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($76,516.77)? | PENDING | — | — |
| SL hit ($75,666.60)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #006 — BTC LONG
<!-- skeptiq:db_id=6 sent_at=2026-04-28T15:53:18.868100 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:53:18 |
| Source | cryptoslate |
| Title | Bitcoin’s comeback is now in the Fed’s hands after big investors piled back in |
| URL | https://cryptoslate.com/bitcoins-comeback-is-now-in-the-feds-hands-after-big-investors-piled-back-in/ |
| Entry | $75,949.99 |
| RSI(14) | 29.0 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.40% |
| Tech alignment | confirms |
| Confidence | 0.60 (base 0.55) |
| Impact / Horizon | high / days |
| SL / TP | $75,666.60 / $76,516.77 |
| Invalidation kind | swing_low |

### LLM thesis
CoinShares data shows crypto investment products recorded $1.2 billion in inflows last week, the third consecutive week above $1 billion, with Bitcoin taking $933 million and Ethereum $192 million. Total AUM reached $155 billion, the highest since Feb. 1, though the Apr. 28-29 FOMC decision is cited as a near-term risk variable.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=006 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($76,516.77)? | PENDING | — | — |
| SL hit ($75,666.60)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #007 — ETH LONG
<!-- skeptiq:db_id=7 sent_at=2026-04-28T15:53:19.125013 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:53:19 |
| Source | cryptoslate |
| Title | Bitcoin’s comeback is now in the Fed’s hands after big investors piled back in |
| URL | https://cryptoslate.com/bitcoins-comeback-is-now-in-the-feds-hands-after-big-investors-piled-back-in/ |
| Entry | $2,273.44 |
| RSI(14) | 35.6 |
| Above EMA20 | no |
| Volume spike | no |
| 24h change | -1.78% |
| Tech alignment | confirms |
| Confidence | 0.60 (base 0.55) |
| Impact / Horizon | high / days |
| SL / TP | $2,258.24 / $2,303.84 |
| Invalidation kind | swing_low |

### LLM thesis
CoinShares data shows crypto investment products recorded $1.2 billion in inflows last week, the third consecutive week above $1 billion, with Bitcoin taking $933 million and Ethereum $192 million. Total AUM reached $155 billion, the highest since Feb. 1, though the Apr. 28-29 FOMC decision is cited as a near-term risk variable.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=007 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($2,303.84)? | PENDING | — | — |
| SL hit ($2,258.24)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #008 — AAVE SHORT
<!-- skeptiq:db_id=8 sent_at=2026-04-28T15:55:28.551988 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:55:28 |
| Source | coindesk |
| Title | Industry leaders are pouring hundreds of millions into a rescue plan for Aave users after massive crypto hack |
| URL | https://www.coindesk.com/tech/2026/04/27/industry-leaders-are-pouring-hundreds-of-millions-into-a-rescue-plan-for-aave-users-after-massive-crypto-hack |
| Entry | $96.20 |
| RSI(14) | 44.2 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.54% |
| Tech alignment | confirms |
| Confidence | 0.67 (base 0.62) |
| Impact / Horizon | high / days |
| SL / TP | $98.86 / $90.88 |
| Invalidation kind | swing_high |

### LLM thesis
A significant hack has targeted Aave, prompting industry leaders to organize a rescue plan involving hundreds of millions of dollars to cover affected users. The full scope of the exploit and the rescue mechanics are not detailed in the available text.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=008 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($90.88)? | PENDING | — | — |
| SL hit ($98.86)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

## #009 — XRP LONG
<!-- skeptiq:db_id=9 sent_at=2026-04-28T15:57:43.947895 -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | 2026-04-28 15:57:43 |
| Source | cryptoslate |
| Title | The South Korean bank powering Upbit is testing Ripple integration for cross-border payments |
| URL | https://cryptoslate.com/south-koreas-internet-only-bank-kbank-k-bank-has-entered-a-strategic-partnership-with-ripple/ |
| Entry | $1.37 |
| RSI(14) | 24.5 |
| Above EMA20 | no |
| Volume spike | YES |
| 24h change | -2.43% |
| Tech alignment | confirms |
| Confidence | 0.60 (base 0.55) |
| Impact / Horizon | medium / days |
| SL / TP | $1.37 / $1.37 |
| Invalidation kind | swing_low |

### LLM thesis
South Korea's Kbank, the sole bank handling KRW real-name account verification for Upbit, has signed a strategic partnership with Ripple to run a proof-of-concept for blockchain-based cross-border remittances. The pilot includes testing on UAE and Thailand corridors and evaluation of Ripple's Palisade wallet and custody platform, but no commercial launch date, settlement asset, or fee model has been confirmed.

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id=009 start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit ($1.37)? | PENDING | — | — |
| SL hit ($1.37)? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---

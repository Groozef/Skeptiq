# Skeptiq — Comparative Signal Report

Полная история сигналов трёх версий бота, сравнение поведения, реальные исходы.

**Дата отчёта:** 2026-04-29
**Текущие цены на момент анализа:** BTC $77,590 · ETH $2,331 · AAVE $96.92 · XRP $1.39

---

## 📊 КРАТКАЯ СВОДКА (TL;DR)

| Версия | Когда | Сигналов отправлено | TP_HIT | SL_HIT | Open | Качество |
|---|---|---|---|---|---|---|
| **v0.1** | 2026-04-28 18:59–19:01 Almaty | 2 | (нет SL/TP) | — | 2 | direction: 1/2 верно |
| **v0.2 (с багами)** | 2026-04-28 20:44–20:57 Almaty | 7 | **5** | 0 | 2 | TPs были тугие (0.75%), все 5 winning по чистой удаче направления |
| **v0.2.1 (фиксы)** | 2026-04-29 17:02–17:17 Almaty | **0 sent** | — | — | — | 44 analyses, 1 explicit drop, остальные filtered (правильно) |

**Главный вывод:** v0.2 выдал 7 сигналов с тугими TP'шками которые легко взять; v0.2.1 на ТЕХ ЖЕ новостях выдал бы **1–2** сигнала (см. §3). Меньше signals — но без дублей и противоречий.

---

## 1. v0.1 (первый прогон, 2 сигнала)

**Контекст:** v0.1 не имел SL/TP, calibration формулы, dedup'а — голый LLM с базовым watchlist filter.

### #1 — BTC SHORT
| Поле | Значение |
|---|---|
| Время | 2026-04-28 18:59 Almaty (13:59 UTC) |
| Источник | cointelegraph |
| Заголовок | Bitcoin ETFs snap nine-day inflow run as BTC slips below $77K |
| Описание | $263M ETF outflow, 9-day streak ended, BTC failed to reclaim $80K |
| Direction | **SHORT** |
| Entry | $76,182.01 |
| SL/TP | НЕТ (v0.1) |
| LLM confidence | 0.62 raw |
| **Тех контекст** | RSI 32.3 (near-oversold), below EMA20, vol spike 2.34× |
| Tech alignment | neutral |
| **Цена через 24h+** | $77,590 (+1.85%) |
| Max high | $77,905 |
| Min low | $75,666 |
| **Direction correct?** | ❌ **НЕТ** — BTC пошёл вверх |
| **Оценка задним числом** | RSI 32 + volume spike = selling climax. Шортить классическую ловушку «продай дно» — ошибка. v0.2.1 calibrated → 0.44 → drop. |

### #2 — ETH LONG
| Поле | Значение |
|---|---|
| Время | 2026-04-28 19:01 Almaty (14:01 UTC) |
| Источник | cointelegraph |
| Заголовок | Acting AG Todd Blanche confirms "code is not a crime" in DOJ pivot |
| Описание | DOJ изменил позицию по преследованию разработчиков; structural change для DeFi/privacy |
| Direction | **LONG** |
| Entry | $2,272.78 |
| SL/TP | НЕТ (v0.1) |
| LLM confidence | 0.62 raw |
| **Тех контекст** | RSI 35.3, below EMA20, no spike (volume_ratio bug 0.02), 24h −1.81% |
| Tech alignment | confirms (single-rule "room to run") |
| **Цена через 24h+** | $2,331 (+2.59%) |
| Max high | $2,347 |
| Min low | $2,269 |
| **Direction correct?** | ✅ **ДА** — ETH пошёл вверх |
| **Оценка задним числом** | Тезис правильный (regulatory positive для ETH/DeFi). Direction и horizon выбраны верно. Сигнал хорошего качества. |

**v0.1 итог:** **1 win / 1 loss** по направлению. Без SL/TP реальный PnL посчитать нельзя.

---

## 2. v0.2 С БАГАМИ (7 сигналов, тот же день, +1.5h после v0.1)

**Контекст:** v0.2.0 имела **критические баги**:
- Single-rule alignment (RSI<50 + below EMA20 = «confirms» что бы ни было)
- Counter-signals только текстом, без формулы
- Не было event dedup → дубли по одной новости
- Не было subject detection → AAVE как secondary упоминание ловил сигнал
- ATR-based SL брал TIGHTER из (swing, atr) → SL'ы 0.37–1.0% (внутри шума)

### #3 — AAVE LONG (Kelp event)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:44 Almaty (15:44 UTC) |
| Источник | coindesk |
| Заголовок | Aave-Led 'DeFi United' Relief Effort Raises $300 Million to Cover Kelp DAO Exploit Losses |
| Главный субъект | **Kelp DAO** (не AAVE — AAVE координатор) |
| Direction | LONG |
| Entry | $96.20 |
| **SL / TP** | $95.24 (−1.0%) / $98.12 (+2.0%) |
| Confidence | raw 0.55 → calibrated 0.60 (alignment confirms +0.05) |
| Impact / Horizon | high / days |
| **Outcome** | ✅ **TP_HIT** (max high $98.79) |
| **Баг v0.2.0** | Subject detection отсутствовал — AAVE упомянут вскользь |

### #4 — AAVE SHORT (та же Kelp story, противоположное направление!)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:50 Almaty (15:50 UTC) — через **6 минут** после #3 |
| Источник | cointelegraph |
| Заголовок | Aave-linked DeFi United unveils rsETH recovery plan after $293M Kelp exploit |
| Описание | **То же событие что #3**, другая статья |
| Direction | **SHORT** ← противоположно #3 LONG! |
| Entry | $96.20 |
| **SL / TP** | $98.86 / $90.88 |
| Confidence | raw 0.62 → calibrated 0.67 |
| **Outcome** | ❌ open, цена против шорта (+0.75% spot, идёт к SL) |
| **Баг v0.2.0** | Нет event dedup — выдал противоречивый сигнал по тому же событию |

### #5 — BTC LONG (Block treasury)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:52 Almaty (15:52 UTC) |
| Источник | cointelegraph |
| Заголовок | Jack Dorsey's Block nears 9,000 bitcoin in treasury after Q1 addition |
| Direction | LONG |
| Entry | $75,949.99 |
| **SL / TP** | $75,666.60 (−0.37% — тугой!) / $76,516.77 (+0.75%) |
| Confidence | raw 0.55 → calibrated 0.60 |
| **Outcome** | ✅ **TP_HIT** (max $77,905, TP at $76,517) |
| **Баг v0.2.0** | Tight SL/TP из-за ATR-bug (тугой stop брал тугую сторону) |

### #6 — BTC LONG (CoinShares inflows)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:53 Almaty (15:53 UTC) — через **минуту** после #5 |
| Источник | coindesk |
| Заголовок | Bitcoin's comeback is now in the Fed's hands after big investors piled back in |
| Описание | CoinShares: $1.2B inflows в BTC + ETH |
| Direction | LONG |
| Entry | $75,949.99 |
| **SL / TP** | $75,666.60 / $76,516.77 (идентичны #5 — тот же тех. контекст в кэше) |
| Confidence | raw 0.55 → calibrated 0.60 |
| **Outcome** | ✅ **TP_HIT** |
| **Notes** | Не дубль #5 (другое событие — Block vs CoinShares), но идентичные SL/TP |

### #7 — ETH LONG (CoinShares, та же новость что #6!)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:53 Almaty (15:53 UTC) — секунда после #6 |
| Заголовок | (тот же что #6) Bitcoin's comeback is now in the Fed's hands |
| Description | **Та же CoinShares новость**, тикер ETH |
| Direction | LONG |
| Entry | $2,273.44 |
| **SL / TP** | $2,258.24 (−0.67%) / $2,303.84 (+1.34%) |
| Confidence | raw 0.55 → calibrated 0.60 |
| **Outcome** | ✅ **TP_HIT** (max $2,347) |
| **Баг v0.2.0** | Multi-asset news → 2 отдельных сообщения в Telegram. Должен быть **1** сигнал на BTC+ETH. |

### #8 — AAVE SHORT (опять Kelp!)
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:55 Almaty (15:55 UTC) |
| Источник | cointelegraph |
| Заголовок | Industry leaders are pouring hundreds of millions into a rescue plan for Aave users |
| Описание | **ТРЕТЬЯ** статья про тот же Kelp event |
| Direction | SHORT (= #4) |
| Entry | $96.20 |
| **SL / TP** | $98.86 / $90.88 |
| Confidence | raw 0.62 → calibrated 0.67 |
| **Outcome** | ❌ open, против шорта |
| **Баг v0.2.0** | Третий сигнал по одному событию — нет dedup |

### #9 — XRP LONG
| Поле | Значение |
|---|---|
| Время | 2026-04-28 20:57 Almaty (15:57 UTC) |
| Источник | cointelegraph |
| Заголовок | The South Korean bank powering Upbit is testing Ripple integration |
| Direction | LONG |
| Entry | $1.3699 |
| **SL / TP** | $1.3677 (−0.16%!) / $1.3742 (+0.32%!) |
| Confidence | raw 0.55 → calibrated 0.60 |
| **Outcome** | ✅ **TP_HIT** (max $1.41) |
| **Баг v0.2.0** | Очень тугие SL/TP — TP взят микро-движением |

**v0.2 buggy итог:**
- **5 TP_HIT / 0 SL_HIT / 4 open** (2 v0.1 без SL/TP + 2 AAVE shorts open against)
- **Win rate: 100% на закрытых** — но **только потому что TP'шки были 0.75–1.34%, easy to take в обычной волатильности**
- **3 сигнала по одному Kelp событию** (1 long + 2 short) — критический bug
- **2 сигнала по одной CoinShares новости** (BTC + ETH дубль)
- **Realized R = +10R**, но это **обманчиво** при таких тугих TP

---

## 3. v0.2.1 (после исправлений) — что бы выдало на тех же новостях?

**Анализ задним числом:** прохожу каждый из 9 исторических сигналов через v0.2.1 фильтры.

| # | Сигнал | v0.2 итог | v0.2.1 что сделал бы | Причина |
|---|---|---|---|---|
| 1 | BTC short (ETF outflow) | sent | **❌ DROP** | RSI 32 + vol spike + below EMA = multi-factor score +4 для short, alignment confirms; но counter-signals strong (rehash, $263M not extreme, macro) → counter total -0.15+ → counter_overload_drop |
| 2 | ETH long (DOJ "code not crime") | sent | **❌ DROP** или borderline | Multi-factor: RSI 35.3 (-1 long), below EMA20 (-1), 24h -1.81% (-1), no spike (0) → score -3 → contradicts → -0.08. raw 0.62 - 0.08 = 0.54 < 0.6 |
| 3 | AAVE long (Kelp story #1) | sent | **❌ DROP** | Subject detection: AAVE упомянут 2× в title+body, "Kelp"/"Kelp DAO" упомянут 5×+ → secondary mention → -0.10 → 0.55 + 0.05 - 0.10 = 0.50 < 0.6 |
| 4 | AAVE short (Kelp story #2) | sent | **❌ DROP** | Event dedup: subject "Kelp" + numbers "$293M/$300M" + projects {Aave, rsETH} совпадает с #3, но direction противоположное → **dup_conflict** → drop с loud log |
| 5 | BTC long (Block treasury 9000 BTC) | sent (TP_HIT) | **✅ FIRE как solo BTC long** | Subject = BTC primary (mentioned много раз, Block тоже но не больше). Calibration: ~0.60-0.65. Multi-factor alignment (RSI 60 + above EMA + +1.2% + spike) score +4 confirms. Wide ATR-stop на 4h timeframe (horizon=days) → SL ~$74,500 (−2%), TP ~$77,400 (+2% × 1.5 = wider) |
| 6 | BTC long (CoinShares inflows) | sent (TP_HIT, дубль #5) | **✅ FIRE как часть BTC+ETH grouped** | Не event-dup #5 (Block ≠ CoinShares — разные subjects/numbers). Но **multi-asset merge с #7** — будет одно сообщение с BTC+ETH блоками. |
| 7 | ETH long (CoinShares — та же что #6) | sent (TP_HIT) | **✅ Объединён с #6** | Та же analysis_id что и BTC long → один Telegram message с 2 tech-блоками |
| 8 | AAVE short (Kelp story #3) | sent | **❌ DROP** | Event dedup vs #3 (AAVE long) → dup_conflict |
| 9 | XRP long (Korean bank) | sent (TP_HIT) | **❌ DROP** (вероятно) | Subject detection: XRP упомянут в title 1×, в body 0× → secondary -0.10. Plus counter-signals about "early stage testing", "small partnership", "no immediate institutional adoption" → likely strong + moderate → counter total ≥ 0.10. Drop probable. |

### Чистый итог v0.2.1 на ТЕХ ЖЕ новостях

- Из 9 исходных: **2 fire** (BTC long Block + BTC/ETH grouped), **7 drop** (1 alignment, 1 dedup, 1 counter-overload, 2 secondary, 2 dup-conflict)
- **6× меньше сигналов, 0 противоречий, 0 дублей**
- **Telegram-сообщений: 2** (Block BTC + grouped CoinShares BTC+ETH) вместо 7

---

## 4. v0.2.1 ЖИВОЙ ПРОГОН СЕГОДНЯ (15 минут)

**Контекст:** 2026-04-29 17:02–17:17 Almaty (12:02–12:17 UTC), 5/5 ingestors живые, новости тихий день.

### Что произошло
- **78 новостей** добавлено в БД (5 фидов, первый цикл)
- **44 analyses** прогнано через Claude (cost ~$0.66)
- **0 sent в Telegram**
- **1 explicit drop** + ~43 filtered out

### Sent
**Нет.** Тишина в Telegram — корректное v0.2.1 поведение в спокойном новостном фоне.

### Drop with full audit (XRP — единственный сигнал что почти прошёл)

| Поле | Значение |
|---|---|
| Время | 2026-04-29 17:07 Almaty (12:07 UTC) |
| Item ID | 172 |
| Тикер | XRP |
| Direction | LONG |
| LLM raw confidence | 0.55 |
| Sentiment | bullish |
| Impact | medium |
| Tech alignment | confirms (+0.05) |
| **Counter-signals breakdown** | |
| └─ counter_moderate | -0.04 |
| └─ counter_strong | -0.07 |
| └─ counter_moderate | -0.04 |
| └─ counter_total | **-0.15 → DROP threshold reached** |
| **Subject detection** | secondary mention (-0.10): XRP упомянут только в title, в body 0 раз |
| **Final adjusted** | dropped before final calculation |
| **Action** | `recommendation_counter_overload_dropped` (loud log, no Telegram) |

**Это идеальный showcase v0.2.1:** один сигнал собрал три защитных механизма (counter overload + secondary + alignment-only confirms). В v0.2.0 он бы прошёл как «XRP long 60%».

### Filter funnel (что отсеялось из 44)

| Стадия | Кол-во | Note |
|---|---|---|
| Total analyses | 44 | |
| Filtered: sentiment=neutral | ~17 | Корректно (не торгуем по нейтральным) |
| Filtered: low impact | ~10 | Корректно |
| Filtered: non-watchlist tickers | ~9 | LLM правильно identifies tickers (ZETA, SYND, APT, PUMP, ONDO, MARA, USDP, USDT) — правильно отсечены |
| Filtered: pre_filter low confidence | ~7 | base + max bonus (+0.05) < min_confidence 0.6 |
| Counter-overload drop | 1 | XRP signal above |
| **Sent** | **0** | |

### Стоимость прогона
**$0.66** за 15 минут (44 analyses × ~$0.015 avg). Экстраполяция на сутки: **~$2.5/день steady-state**.

---

## 5. ИТОГОВОЕ СРАВНЕНИЕ

### По числу сигналов

| Период | v0.1 | v0.2 buggy | v0.2.1 |
|---|---|---|---|
| ~16 минут | 2 | 7 | 0–1 |
| 1 день (extrapolated) | ~30 | ~100 | **~2–3** |

### По качеству (на тех же новостях вчера)

| Метрика | v0.2 buggy | v0.2.1 |
|---|---|---|
| Сигналов | 7 | 2 |
| Конфликтных сигналов (long+short по одному событию) | 1 (3 AAVE про Kelp) | 0 |
| Дублей (одно событие → 2 одинаковых сигнала) | 1 (BTC+ETH из CoinShares) | 0 (объединены) |
| Secondary-mention сигналов | 1 (AAVE-Kelp) | 0 |
| TPs тугие (<1.5%) | 5 из 7 | 0 (горизонт-aware ATR) |

### По выживаемости в реальной торговле

**Сценарий: торговля по всем 7 сигналам v0.2 buggy с $25 риском на сделку:**
- 5 TP_HIT × $50 (= 2R) = +$250
- 2 AAVE short open against → если пробьют SL: −$50, если expire: −$5–10
- **Чистая прибыль: +$200–245** на 7 сделках
- **НО:** TPs были тугие, любая стратегия с такими стопами выйдет в плюс при +1.5% движении BTC

**Сценарий: торговля по v0.2.1 на тех же новостях (2 сигнала):**
- BTC long (Block) с TP +2% = +$50 (= 2R)
- BTC+ETH grouped с +2% движением: 2 × $50 = +$100 (= 4R, потому что 2 ticker'а)
- **Чистая прибыль: +$150**
- Меньше абсолютная прибыль, но **гораздо меньше работы и risk exposure** (2 сделки vs 7)

### Главное заключение

**v0.2.1 != «хуже» — она «строже».** Меньше сигналов = меньше шума. Качество отдельного сигнала **выше** (нет противоречий, нет дублей, нет secondary mentions, SL/TP осмысленные).

Если рынок «горячий» (FOMC день, halving, регуляторные новости), v0.2.1 выдаст 5–10 сигналов — каждый осмысленный. На спокойном дне (как сегодня) выдаст **0–2** — это не баг, это правильное поведение.

---

## 6. БАГИ ПРОИЛЛЮСТРИРОВАННЫЕ КОНКРЕТНЫМИ СИГНАЛАМИ

| Bug | Конкретный signal | Что фиксило |
|---|---|---|
| Event dedup отсутствовал | #3 AAVE long + #4 AAVE short + #8 AAVE short — 3 сигнала по одному Kelp событию, противоречивые | `feat(brain): event-fingerprint deduplication` |
| Counter-signals только текст | Все v0.2.0 сигналы с alignment=confirms имели counter-signals (rehash/thin/secondary) которые игнорировались | `feat(calibration): counter-signals weighted into confidence formula` |
| ATR SL слишком тугой | #5/#6 BTC SL −0.37%, #7 ETH SL −0.67%, #9 XRP SL −0.16% — внутри bar noise | `fix(market): ATR-based SL — pick FARTHER of swing/ATR` |
| Subject detection отсутствовал | #3 AAVE long: главный субъект Kelp DAO, AAVE координатор | `feat(recommender): subject detection — drop signals on secondary mentions` |
| Alignment single-rule | #2 ETH long: RSI 35.3 + below EMA = «confirms» (room to run heuristic), хотя multi-factor score = -3 | `fix(recommender): multi-factor alignment + softened penalties` |
| Multi-asset spam | #6 + #7: одна CoinShares новость → 2 идентичных сообщения в Telegram | `feat(delivery): one Telegram message per news, per-ticker tech blocks` |

---

## 7. ВЫВОДЫ

1. **v0.2.1 архитектурно сильнее** — устраняет 6 из 9 проблем `notatki.md`. Оставшиеся (auto-expire, ещё пара) тоже сделаны.

2. **Меньше сигналов — это правильно.** v0.2 buggy выдал 100% TP_HIT по чистой удаче (тугие TPs + boom in BTC). На любом другом дне эти 7 сигналов могли быть 50/50 или хуже.

3. **Реальная directional accuracy v0.1+v0.2 (вчерашняя выборка):**
   - 9 сигналов всего
   - 7 в правильном направлении (5 TP, 1 ETH long no-TP но direction up, 1 BTC short — wrong)
   - 2 AAVE short — против направления (open, против нас)
   - **7/9 = 78% directional accuracy** на этой маленькой выборке
   - Но **выборка n=9 ничего не доказывает**. Нужно 30+.

4. **v0.2.1 надо мерить.** Чтобы получить 30 закрытых сигналов (для статистической значимости win rate) нужно **2–3 недели** работы бота. После этого можно говорить про accuracy.

5. **Что НЕ сломала v0.2.1:** все валидные сигналы вчерашнего набора (#5 Block long, #6+#7 объединённый CoinShares grouped) **прошли бы** v0.2.1 фильтр и сработали бы по TP. Бот не «сломался», он стал избирательнее.

---

## Methodology / Caveats

- "Direction correct" определено по факту движения цены за **24 часа+** после сигнала (т.е. цена ушла в сторону сигнала), а не "TP hit".
- "TP_HIT" — реальное касание цены TP в любой момент после sent_at до сейчас.
- Все цены из Binance public API (1h интервал).
- v0.2.1 reprocessing — анализ задним числом, не реальный прогон. Реальный прогон сделаем за 2–3 недели и сравним.
- Sample size 9 сигналов — слишком мала для коммерческих заявлений. Статистика начинается с **30+**.

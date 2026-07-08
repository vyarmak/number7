# 06 — Deep Learning & LLM Agents
*Trading System Knowledge Base · theme T06 · equities/ETF-weighted*
*Updated: added the Tatsat et al. (ML & DS Blueprints) DQN trading-bot blueprint, and Coqueret & Guida's RL-for-allocation critique + custom-loss tip.*

**What this covers:** When deep learning (DL) earns its keep over classical ML for trading; the DL architecture zoo for markets (MLP, RNN/LSTM/GRU, CNN incl. time-series-as-image, autoencoders, GANs/TimeGAN) with input shapes, design choices, and financial-TS gotchas; deep reinforcement learning (DRL) as a trading agent; NLP/embeddings for sentiment and return prediction; and the emerging **LLM-agent** stack (ATLAS, FINMEM) with reusable agent patterns (memory, reflection, tool-use, multi-agent). It closes with how to backtest DL/agent strategies honestly.

**Why it matters:** DL and LLM agents are the highest-variance, highest-hype corner of quant. Used well, they capture nonlinear interactions and unstructured-text alpha that linear models miss; used naively, they overfit catastrophically on low-signal financial data. This file is the map of what is actually actionable versus illustrative.

**Primary sources:** Jansen, *ML for Algorithmic Trading* (DL/RL chapters 18–22); Kaabar, *Deep Learning for Finance* (NN foundations + architectures); ATLAS (Papadakis et al.) and FINMEM (Yu et al.) for LLM agents; Wellman et al., *Autonomous Bidding Agents* (multi-agent evaluation); Guo, Lai, Shek & Wong (*Chinese Quant*) and Narang, *Inside the Black Box* for framing.

---

## 1. When deep learning is (and isn't) worth it

DL is not a free upgrade over gradient-boosted trees and linear factor models. Reach for it only when the data structure justifies it:

- **Match architecture to data structure** (Jansen p.817, 838). CNNs exploit *local* grid patterns (indicator images, satellite imagery, autocorrelation at specific lags). RNN/LSTM/GRU model *sequences* where each output depends on prior state (returns, text). If there is no temporal-memory or local-pattern structure to exploit, a feedforward net — or plain regression — is the right tool, and often wins.
- **Financial time series carry very low signal.** This is the single most important fact in the file. Across Jansen's CNN/RNN/autoencoder experiments, the best models train for only **~4–9 epochs** before early stopping, daily information coefficients (ICs) are tiny (~0.009 for CNN-TA, 0.02–0.03 for the conditional autoencoder), and "slight modifications yield significantly worse performance" (Jansen p.832). Kaabar's daily S&P 500 classifiers land near coin-flip test accuracy (MLP 54.9%, LSTM 50.4%, CNN 49.2%) despite 90%+ train accuracy — textbook overfitting (Kaabar p.227–246).
- **Overkill is a real failure mode.** Kaabar shows linear regression hitting R²=0.935 on a differenced oscillating series where an LSTM would be pointless (Kaabar p.239–242). "Deep" (≥2 hidden layers) is a cost, not a virtue.
- **Interpretability is the price of admission for capital.** Black-box adoption needs SHAP-style per-feature attribution so you can check the model's logic against market theory (Jansen p.1012); Guo et al. likewise treat explainability as a governance requirement, not a nicety. FINMEM explicitly markets interpretability and real-time inspectability of its memory module as an edge over DRL black boxes (FINMEM p.1–2).
- Narang's framing is worth keeping: parsing plain-English news or alt-data with ML is a faster *fundamental/sentiment* input, not a new strategy class (*Inside the Black Box* p.136–137). DL changes the feature pipeline more often than it changes the strategy.

**Bottom line:** expect tiny, fragile signals (ICs ~0.01–0.03). Always ensemble best epochs/folds to cut forecast variance, validate on time (never shuffle), and convert predictions to a long-short spread before believing them (Jansen p.830–832).

---

## 2. DL architectures for markets

**Shared foundations (Kaabar Ch.8):** a neuron is a weighted sum + activation; training is forward-prop → loss → **backprop** (chain rule) → optimizer step over epochs/batches. Defaults that recur everywhere: **ReLU** activation (`max(0,x)` — fast, mitigates vanishing gradients, but can "die"; leaky ReLU fixes dead neurons), **Adam** optimizer, MSE loss for regression, batch size ~32 (Kaabar p.217–226). Anti-overfitting toolkit: **dropout**, **early stopping** with `restore_best_weights`, **batch normalization**, L1/L2 weight decay (Kaabar p.226–227, 271–276).

### Feedforward / MLP
`Dense(20,relu) → Dense(20,relu) → Dense(1)`, input 2D `(samples, num_lags)`. Use when no temporal-memory structure is needed. Highly hyperparameter-volatile (Kaabar p.227–231).

### RNN / LSTM / GRU (sequence modeling)
- **When:** sequential data with memory — many-to-one (sentiment), many-to-many (multistep multivariate forecast). A nonlinear alternative to VAR models (Jansen p.838, 866).
- **Mechanics:** trained by *backpropagation through time* (sequential, expensive). Vanilla RNNs hit vanishing/exploding gradients beyond ~10–20 steps (Jansen p.844). **LSTM** adds forget/input/output gates so gradients pass unchanged; **GRU** drops the output gate — fewer params, trains faster, and **does better on smaller datasets** (Jansen p.845–847). For noisy financial data, prefer GRU.
- **The universal gotcha — input tensor shape `(batch, time_steps, features)`.** LSTM/CNN need 3D input; reshape `(-1, num_lags, 1)` for a single feature (Kaabar p.235; Jansen p.848). Scale series to [0,1] with `MinMaxScaler`; build overlapping rolling windows. **RMSProp** is the recommended optimizer for RNNs (Jansen p.852).
- **Variants:** stacked LSTMs (`return_sequences=True` on lower layers) for hierarchical representations; **bidirectional** RNNs for text/SEC filings; encoder-decoder (seq2seq) for variable-length; **attention** and **transformers** (drop recurrence, parallelizable, SOTA) when you have enough data to feed them (Jansen p.840–842).
- **Mixed-input pattern (Functional API):** fuse a return sequence + a **learned Embedding for ticker** (~5-dim for thousands of stocks) + one-hot month → concatenate → BatchNorm → Dense. Lets one net blend sequential + categorical + fundamental features (Jansen p.854–862). Beware: a single-LSTM *level* predictor on the S&P 500 scored test IC 0.989 only because price levels are trivially autocorrelated — predict returns, not levels (Jansen p.848–853).

### CNN (incl. time-series-as-image)
- **When:** grid-like data where local patterns predict the outcome; ordering matters (unlike FFNs) (Jansen p.817).
- **1D autoregressive conv:** `Conv1D(filters=32, kernel_size=4, padding='causal') → MaxPool → BatchNorm → Dense(1)`. **Causal padding is mandatory** to preserve temporal order and avoid leakage (Jansen p.820). In Kaabar's framing, kernel_size = receptive field (small = short-term, large = long-term) (Kaabar p.243–246).
- **CNN-TA (2D image of indicators):** compute ~15 technical indicators (RSI, WMA/EMA, ROC, ADX, PPO, Bollinger, rolling Fama-French betas) across 15 lookback windows → a 15×15 grid. Select features by **mutual information**; **order rows/cols by hierarchical (Ward) clustering** so similar indicators sit adjacently (CNNs assume locality). Scale to [-1,1] (Jansen p.823–828). Result: 35.6% cumulative return, Sharpe 0.53 pre-cost on 500 US stocks (p.832). **Caveat:** with low SNR, an over-complex net collapses to predicting a constant — fixing features matters more than tuning the net (p.832).
- **Transfer learning (alt-data):** load pretrained net `include_top=False` for bottleneck features, freeze the conv base, append GlobalAveragePooling → Dense → Dropout → output, **train the head FIRST**, then optionally unfreeze conv layers (fine-tuning before the head is trained wipes pretrained weights with huge random gradients) (Jansen p.801–809). Use cases: crop/harvest classification, counting oil tankers or cars in lots (EuroSat transfer hit 97.96%, p.811).

### Autoencoders (conditional factor model — the headline equity application)
- **What:** self-supervised nets that reconstruct their input; the bottleneck code is a **nonlinear generalization of PCA** (Jansen p.884). Variants: undercomplete (compression), **sparse** (L1 `activity_regularizer`), **denoising** (anomaly/illegal-trade detection), convolutional, seq2seq, and **VAE** (generative) (p.884–889).
- **Conditional Autoencoder (Gu-Kelly-Xiu 2019/20) — the most directly actionable equity model in this file.** Models returns as a **dot product of factor loadings × factor premia**. LEFT branch: feedforward net maps P asset *characteristics* → K factor *loadings* (betas). RIGHT branch: autoencoder maps N asset *returns* → K factor *premia*. Output = β·premia; risk factors are treated as latent/statistical (a nonlinear extension of Fama-French/IPCA), predicting t from t-1 (Jansen p.899–914).
  - **Preprocessing (load-bearing):** rank-normalize each characteristic cross-sectionally to **[-1,1] per date**; set missing values to **-2** (outside the valid range so the net learns to ignore them); account for reporting lags to avoid snooping (p.905–909).
  - **Design:** Functional API, `Dot(axes=(2,1))`, MSE + Adam, K in 2–6, hidden units 8/16/32. Best config: **more factors (4–6), fewer hidden units (8)** → IC 0.02–0.03, ~10bps long-short decile spread at 5-day horizon. Add L1 penalties, multi-seed ensembling, early stopping, and **value-weighted** LS regression to avoid microcap dominance (p.909–912).

### GANs / TimeGAN (synthetic data)
- **Why for trading:** limited historical data is a *prime driver of backtest overfitting*; synthetic data could expand training/backtest sets and feed model-based RL (Jansen p.917, 952).
- **Mechanics:** generator vs discriminator in a zero-sum game, competing binary-cross-entropy losses, Adam at low LR (1e-4), separate optimizers. Training is notoriously unstable (p.918, 927).
- **TimeGAN (Yoon et al. 2019):** combines reconstruction + unsupervised (adversarial) + **supervised stepwise** losses, plus a **moment loss** matching synthetic mean/variance to real. An embedding (autoencoder) network runs the adversarial game in a lower-dim latent space, which regularizes training. Implemented with stacked GRUs; generator trained 2× as often as the discriminator (p.930–945). Less hyperparameter-sensitive than typical GANs.
- **Evaluate synthetic data on three axes:** **Diversity** (PCA/t-SNE overlap of real vs synthetic), **Fidelity** (train a classifier to tell real from fake — *high* error ≈56% means indistinguishable = good), **Usefulness** (train-on-synthetic, test-on-real, "TSTR") (p.945–952). Caveat: demonstrated on only 6 tickers, daily, prices not returns — unproven at realistic cross-sectional scale (p.952).

---

## 3. Deep reinforcement learning for trading

- **Why RL fits:** it is interactive, online, and goal-directed, modeling the investor's actual sequential task (Jansen p.954, 1000). But noise + delayed rewards make value-function learning especially hard.
- **MDP formulation:** *state* (features — must be **stationary**: RSI/MA/lagged returns, not raw price), *action* (buy/sell/hold), *reward* (return / Sharpe / −drawdown), policy, value function. Agent maximizes discounted return; γ<1 (Kaabar p.277–290; Jansen p.956–967).
- **Reward design is the hardest, most critical part** — specify *what* to achieve, not *how*; for trading, P&L plus volatility/drawdown terms (Jansen p.958). Two core challenges: **credit assignment** (rewards lag the causal action) and **exploration vs exploitation** (ε-greedy) (p.960–961).
- **Solution ladder:** DP value/policy iteration (needs known transitions) → **Q-learning** (model-free, off-policy: `Q(s,a) ← Q(s,a) + α[r + γ·max Q(s',a') − Q(s,a)]`) → **Deep Q-Network**. DQN/DDQN stabilizers: **experience replay** (random mini-batches break autocorrelation; *prioritized* replay samples by TD-error), **target network** (slow-moving copy generates TD targets), **Double DQN** (online net selects the action, target net values it → fixes Q overestimation) (Jansen p.962–984).
- **Custom OpenAI Gym env (Jansen p.991–999):** three classes — `DataSource` (loads OHLCV, builds stationary features, serves one observation/step), `TradingSimulator` (tracks position, NAV vs a frictionless buy-and-hold benchmark, costs), `TradingEnvironment` (`spaces.Discrete(3)` actions, `spaces.Box` state). **Actions are discrete (long/flat/short)** to deliberately dodge continuous position sizing. **Reward = daily return × position − trading cost** (10bps/trade). Agent: DDQN, 2×Dense(64)+dropout (~5,000 params), γ=0.99, ε decay 1.0→0.1.
- **Pitfalls:** **single-stock training massively overfits** — the agent beats buy-and-hold >50% of the time only after ~500 episodes on one ticker; generalize across assets, add position sizing and risk management before trusting it (p.999–1000). Kaabar flags RL as **not yet production-ready** for trading (Kaabar p.290). **Always benchmark against both buy-and-hold AND a random agent** (Jansen p.997).
- **A second worked DQN blueprint (Tatsat et al., *ML & DS Blueprints*, ch.9):** *state* = sigmoid of past price differences over a τ-window (normalized to [0,1]); *actions* = buy/sell/hold; *reward* = realized P&L on a sell (0 otherwise, extendable with vol/drawdown/cost terms); Keras net Dense 64→32→8 ReLU with 3 linear Q-outputs; γ=0.95, ε-greedy decay 0.995 (1.0→0.01), experience-replay buffer, Bellman target. On 10y daily S&P 500 it booked ~$1,280 on the held-out set. The authors argue RL "folds backtesting + parameter optimization into training" and is more regime-robust than a fixed supervised policy — but with **low interpretability**, so test across regimes before trusting it (this echoes the overfitting caution above). They also offer LSTM (ch.5) and BERT (ch.10) blueprints for return forecasting and news sentiment.
- **Why RL struggles for multi-asset allocation (Coqueret & Guida, *ML for Factor Investing*, ch.16):** the MDP has *states* ≈ feature/macro levels and *actions* ≈ portfolio weights on the N-asset simplex, solved by **Q-learning** (off-policy) or **SARSA** (on-policy) with ε-greedy exploration. But it hits a brutal **curse of dimensionality** — e.g. 10 values × 10 features × 10 stocks ⇒ ~10^100 (state,action) cells, while a few hundred monthly observations give ~2 samples per cell (incoherent policy); and crucially **the agent's trades don't move the environment**, undercutting standard RL feedback. Verdict: promising for *non-stationary, online* adaptation (it converges to the static optimum under stationarity) but not yet competitive with supervised methods on high-dimensional books. A practical NN tip from the same source: networks uniquely allow **custom loss functions** — optimize a correlation/direction objective (Σ y·ŷ) rather than MSE when the goal is ranking, not point accuracy.

---

## 4. NLP for trading (embeddings, sentiment)

- **Pipeline:** tokenize → integer-encode → `pad_sequences` to fixed length → Embedding → GRU/LSTM → Dense (Jansen p.867–869).
- **Train your own embeddings** on financial text when you can — task-specific vectors (reflecting the *outcome*, e.g. sentiment) beat frozen pretrained **GloVe** (IMDB AUC 0.939 vs 0.911) (p.869–872).
- **SEC-filings return prediction (equities-relevant):** 16k+ 10-K/10-Q filings → 5-day forward return. Architecture: Embedding(100) → BatchNorm → **Bidirectional GRU(32)** → Dropout → Dense(1). Significant test **IC 6.02 from text alone** — but flagged with **point-in-time risk** (after-hours filing assumption may cause lookahead), noisy parsing, and arbitrary horizon/vocab choices; combine text with numeric features (p.873–879).

This is the bridge to **file 10 (Alternative Data & NLP)** — sentiment sourcing, news ingestion, and embedding infrastructure live there.

---

## 5. LLM-agent trading systems

A newer paradigm: an LLM (or several) reasons over market context and emits decisions, with scaffolding for memory, prompt adaptation, and execution. Two reference designs.

### ATLAS (Papadakis et al.) — multi-agent pipeline + adaptive prompting
- **Architecture (3 components):** a **Market Intelligence Pipeline** (specialized analyst agents that prepare inputs), a **Decision & Execution Layer** around a **Central Trading Agent (CTA)** that emits/executes orders, and a **Feedback Mechanism** for continuous adaptation. Information preparation is deliberately separated from decision-making (p.2).
- **Analyst roles (structured output, not signals):** **Market Analyst** (multi-timescale price/volume summaries — 2y monthly / 6m weekly / 3m daily — with MAs, momentum, vol bands, support/resistance), **News Analyst** (articles compressed into four fixed fields: Sentiment, Key Developments, Market Relevance, Source Analysis, with optional full-text retrieval to reduce headline bias), **Fundamental Analyst** (material changes from periodic reports, activating infrequently to mirror reporting cycles) (p.2, p.12–13). Crucially, indicators are presented as **descriptive context, explicitly not as trading signals**.
- **Coordination = pipeline → central-decider, NOT debate.** Analysts feed structured summaries to one CTA, which adds current portfolio state and emits orders. A single LLM backbone runs all components per experiment to isolate model-capacity effects (p.2, p.4).
- **Order-level action space** is the key implementation choice: the CTA must submit fully executable orders (type, side, size, price) into the **StockSim** order-level simulator, which enforces cash/inventory/validity and returns fills — yielding a complete audit trail. Microstructure is abstracted (deterministic fills, no slippage/latency) so observed differences come from *decision policies* (p.4–5, p.9–11). Behavioral finding: weaker models "generate plausible market analysis but fail in position sizing, timing, or order selection" — **execution discipline, not analysis, separates winners** (p.7).
- **Adaptive-OPRO (dynamic prompt optimization):** extends OPRO ("LLM as meta-optimizer over instruction text") to sequential, delayed-reward settings. Maintains current prompt P_t + an **optimization history H = {(P_i, s_i)}**; at each window end an **optimizer LLM** diagnoses failure modes, proposes a revision, and states expected impact, producing P_{t+1} (p.3).
- **Template separation / edit locality:** the CTA prompt is split into an editable **static-instructions block** (policy, constraints, formatting) and a frozen **dynamic run-time block** (state, observations, tool outputs). **Only the static block is editable**; placeholders/injection format are frozen. This changes *how* the agent reasons but not *what* it receives — preventing schema breakage and overfitting to transient observations (p.3).
- **Windowed scoring:** prompts are evaluated over rolling windows of **K=5 trading days**; cumulative ROI maps to a bounded score via `s = clip[0,100](50 + 250·ROI)`. Candidates are accepted only if they preserve required placeholders/output schema (p.4).
- **Key results & lessons:** Adaptive-OPRO consistently beat both the static baseline and reflection across models/regimes (e.g. GPT-o3 bearish-volatile −6.11% → +9.02% ROI), with **stable/lower drawdowns and higher win rates — more consistency, not bigger gambles** (p.5–6). The **"reflection paradox":** naive weekly reflection often *hurts*, and hurts stronger models more (r=−0.78) — it can override useful heuristics and amplify stochasticity ("overthinking," a machine analogue of analysis paralysis) (p.7). Ablations: the Market Analyst is the most load-bearing input; the News Analyst is critical in sideways markets — but **more modalities ≠ better** (dropping news sometimes *raised* ROI in clean bullish trends) (p.8).

### FINMEM (Yu et al.) — layered decaying memory + persona
- **Architecture (3 modules):** **Profiling** (agent character/background + risk inclination), **Memory** (layered message processing), **Decision-making** (convert retrieved memories + current market into decisions). Inspired by Park et al.'s Generative Agents but redesigned for financial data of **varying timeliness** (p.1–2).
- **Layered memory:** **Working memory** is a dynamic workspace for summarization, observation, and reflection. **Long-term memory** has three layers (shallow / intermediate / deep, per Craik & Lockhart's levels-of-processing) with **different decay rates matching data timeliness** — daily news → shallow, annual reports → deep. Each layer ranks events by **recency + relevancy + importance**, and highly impactful memories can be **promoted to deeper layers** for longer retention (p.2).
- **Persona / risk preference:** a trading-task-specific professional background plus a **self-adaptive risk-inclination** that updates continuously to market fluctuations — risk management is embedded in the persona rather than as explicit sizing rules (p.2).
- **Perception → memory → decision loop + cognitive span:** perceived multi-source data is routed to the matching memory layer; decisions synergize top retrieved memories with current conditions. The **"cognitive span"** (number of events retrieved per layer) is a **tunable knob** that lets the agent exceed the human 5–9 item working-memory limit (Miller 1956) for richer decisions (p.2). FINMEM claims SOTA performance from a short, low-volume training window even with general-purpose LLMs — but the available excerpt reports **no numbers** (p.1–2).

### Reusable agent design patterns
- **Memory** — layer by data timeliness; rank by recency/relevancy/importance; promote high-impact events (FINMEM).
- **Reflection** — useful but dangerous: prefer a windowed, history-aware **optimizer** over naive periodic reflection under noisy reward (ATLAS reflection paradox).
- **Tool-use / structured I/O** — pre-digest inputs into stable, schema-consistent fields; keep the decision agent's interface fixed across assets/regimes (ATLAS).
- **Multi-agent topology** — separate analysis from execution (pipeline → central decider); an **order-level** action space makes failures attributable and produces an audit trail.
- **Persona/risk encoding** — make behavior steerable and interpretable (FINMEM).
- **Multi-agent debate** is a known alternative pattern, but note ATLAS deliberately chose pipeline-to-decider *over* debate.

A complementary lesson from classical multi-agent theory (Wellman et al.): **a trading agent's performance is intrinsically a function of the other agents' strategies.** There is no strategy optimal in all contexts, and **self-play is not a sufficient test** — evaluate against *heterogeneous* opponents. Use empirical game theory to find robust (ε-Nash) profiles; model rivals explicitly but **self-monitor model validity and revert to a safe default when the model stops fitting** (Walverine's design) (Wellman et al. p.122–157, 180–189). This discipline transfers directly to validating an LLM agent against varied counterparties and regimes.

---

## 6. How to backtest & evaluate DL/agent strategies honestly

- **Validate on time, never shuffle.** Use `MultipleTimeSeriesCV` — train on a multi-year window, predict the next short block, roll forward (e.g. 36 folds of 5yr-train/1mo-test) (Jansen p.821, 829). Checkpoint weights every epoch to pick best epochs without retraining (p.830).
- **Signal evaluation pipeline:** predictions → Alphalens quintile/decile spread → long-short (e.g. top/bottom 25 names daily) → Sharpe *before* costs (p.831).
- **Backtest overfitting is THE challenge** — worse than web-scale ML because of low SNR and small datasets. No clean fix; mitigate with **deflated Sharpe** (accounts for repeated trials), staged paper-trading, and monitored live execution before scaling (Jansen p.1011–1012). Learning curves diagnose bias (underfit → add features) vs variance (overfit → more data) (p.1010).
- **Look-ahead / leakage is acute with news + LLMs.** Third-party timestamps must reflect *when information was actually available* (the SEC after-hours assumption is flagged as a likely lookahead error, Jansen p.875, 1006). For LLM agents specifically, the backbone may have been **pretrained on the test window** — ATLAS uses no-lookahead bar handling and timestamped news but admits it cannot rule out **pretraining memorization** of well-known tickers (ATLAS p.80).
- **Baselines are mandatory.** Benchmark DRL against buy-and-hold AND a random agent (Jansen p.997); benchmark LLM agents against Buy & Hold, MACD, SMA, Bollinger — which are themselves **regime-dependent and fail to generalize** (Buy & Hold −8.59% bearish vs +41.3% bullish in ATLAS) (ATLAS p.5–6).
- **Run every config multiple times and report mean ± std** — LLM stochasticity is large enough to flip single-run conclusions (ATLAS runs each config 3×) (p.4–5).
- **Match the adaptation/credit-assignment window to the reward delay** (ATLAS K=5 days).

Full backtesting methodology — deflated Sharpe, walk-forward, combinatorial purged CV — lives in **file 07 (Backtesting & Validation)**.

---

## Cross-references
- **05 — Classical ML for Trading:** trees/boosting baselines DL must beat; feature engineering and `MultipleTimeSeriesCV`.
- **07 — Backtesting & Validation:** deflated Sharpe, walk-forward, leakage controls (depended on throughout §6).
- **08 — Risk Management & Position Sizing:** ATLAS order-level risk primitives; FINMEM risk-inclination persona.
- **10 — Alternative Data & NLP:** embeddings, news/sentiment sourcing and ingestion (extends §4).
- **11 — System Architecture:** TF2/Keras Functional API, GPU infra, Spark, simulator design (StockSim, custom Gym env).

## Caveats on DL/LLM-agent trading claims
- **Signals are tiny and fragile.** Daily ICs of 0.01–0.03 and <10-epoch training are the norm; "slight modifications yield significantly worse performance" (Jansen p.832). Never trust a single configuration — ensemble and roll-forward.
- **DRL and LLM agents overfit hard at small scope.** Single-stock RL training "massively overfits" (Jansen p.1000); ATLAS is 3 stocks / 2-month windows / daily decisions — behavioral evidence about a *mechanism*, not market-wide performance, and FINMEM's excerpt gives **no numbers at all**.
- **No microstructure in agent evals.** Deterministic fills, no slippage/partial-fills/latency/intraday — absolute returns will differ under real execution (ATLAS p.79).
- **Pretraining leakage can't be ruled out** for LLM agents tested on recent, well-known tickers (ATLAS p.80); GAN synthetic data is "very early days" and unvalidated at realistic scale (Jansen p.952).
- **The optimizer/reflector is itself a fallible LLM** — ATLAS reports models inventing edits not in the prompt or drifting to over-restrictive prompts; reflection can *degrade* strong agents (the reflection paradox).
- **Production-readiness is not established.** Kaabar flags RL as not production-ready (p.290); both agent papers state results are simulated and not financial advice. Robustness across assets, horizons, sectors, and macro regimes is untested.

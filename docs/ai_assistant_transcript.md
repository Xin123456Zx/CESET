# CESET AI assistant — unedited session transcript

This file records a **complete, unedited** run of the built-in assistant against a live CESET session, so the assistant can be judged on more than the few minutes of the demo video. Every question below was sent to the running backend in one sitting; the answers, the retrieved sources, and the response times are exactly what the tool returned. Nothing was re-rolled or hand-edited.

Captured: 2026-08-14 · model `claude-sonnet-5` · knowledge base: 248 chunks from 6 documents · retrieval: BM25 (top-6, positive scores only).

## The session the assistant was answering about

The questions marked *state-aware* were asked while the tool held this real state — a context field, a region of interest, a completed ROI optimization, and a completed sensitivity analysis. The numbers below were produced by the backend, not by hand:

```json
{
  "context_params": {
    "omM": 0.14,
    "omB": 0.0225,
    "h": 0.72
  },
  "roi_view_axes": [
    64,
    192,
    64,
    192,
    64,
    192
  ],
  "reference": "pred",
  "uncertainty_preference": {
    "data": "max",
    "model": "max"
  },
  "current_eval": {
    "aleatoric": 0.024419499561190605,
    "epistemic": 0.010277348570525646,
    "params": [
      0.14,
      0.0225,
      0.72
    ],
    "value": 0.0
  },
  "recommendations": [
    {
      "rank": 1,
      "params": [
        0.140005,
        0.0225004,
        0.720008
      ],
      "rmse_vs_reference": 1.807464554816614e-05,
      "aleatoric": 0.024417972192168236,
      "epistemic": 0.010276632383465767
    },
    {
      "rank": 2,
      "params": [
        0.139411,
        0.022209,
        0.721402
      ],
      "rmse_vs_reference": 0.0023918033026136933,
      "aleatoric": 0.02455795742571354,
      "epistemic": 0.010342356748878956
    },
    {
      "rank": 3,
      "params": [
        0.139519,
        0.0224268,
        0.719013
      ],
      "rmse_vs_reference": 0.0026222373532198543,
      "aleatoric": 0.024635007604956627,
      "epistemic": 0.010378335602581501
    }
  ],
  "parameter_sensitivity": {
    "note": "mean |d(ROI-mean prediction)/d(normalized param)| over a full-range sweep, computed by autograd on the surrogate",
    "OmM": 0.0908554359560921,
    "OmB": 0.11693799389260155,
    "h": 0.18370407474936828
  }
}
```

(The assistant received all 6 recommendations; the first three are shown here for brevity.)

## Summary

| # | Capability probed | Question | Response time |
|---|---|---|---|
| Q1 | Concept explanation | What is the difference between aleatoric and epistemic uncertainty, and how should I read the two uncertainty volumes in View 1? | 13.0 s |
| Q2 | Interface / workflow guidance | How does Recommend Parameters work in the Para-space view? | 11.2 s |
| Q3 | Method grounding with citations | Why do the calibrated intervals have a coverage guarantee, and what assumption does that rely on? | 16.4 s |
| Q4 | Answer conditioned on live session state | Look at my current recommendations: is candidate #1 actually better than my current parameters, and why was it ranked first? | 34.7 s |
| Q5 | Answer conditioned on live session state | In my current ROI, which simulation parameter has the strongest influence on the prediction? | 4.7 s |
| Q6 | Out-of-scope probe (must refuse) | What was the CPU wall-clock time of the original Nyx simulation for ensemble member 293? | 2.3 s |

## Full exchanges

### Q1 — Concept explanation

**Question.** What is the difference between aleatoric and epistemic uncertainty, and how should I read the two uncertainty volumes in View 1?

*Live session state sent with the question: no · response time 13.0 s · mode `llm`*

**Answer.**

> Aleatoric and epistemic uncertainty represent two distinct sources of predictive uncertainty:
> 
> **Conceptual difference**
> - **Aleatoric (data) uncertainty** reflects inherent randomness in the underlying data itself — e.g., sensitivity to initial conditions, limited spatial resolution, or numerical truncation/rounding in the ensemble simulations. It is irreducible: you cannot lower it just by training on more data or improving the model [6].
> - **Epistemic (model) uncertainty** reflects the surrogate model's own ignorance — approximation error and, especially, lack of training data coverage. It arises because ensemble datasets are typically sparse, forcing the model to extrapolate in poorly covered regions of parameter/simulation space. Unlike aleatoric uncertainty, epistemic uncertainty can in principle be reduced by adding more/better training data [6].
> 
> In the Deep Evidential Regression (DER) framework this tool uses, a single forward pass predicts the four parameters of a Normal-Inverse-Gamma distribution (gamma, v/nu, alpha, beta) per point, which lets the model disentangle these two effects rather than reporting only one combined uncertainty [5].
> 
> **How the two uncertainty volumes are computed and should be read in View 1**
> View 1 shows three volume renderings per history record — prediction, aleatoric uncertainty, and epistemic uncertainty — all derived from the same DER outputs (gamma, v, alpha, beta) [from tool semantics]:
> 
> - **Prediction**: `gamma * 4.03 + 8.77` (denormalized log10 density) [1].
> - **Aleatoric uncertainty volume**: `sqrt(beta / (alpha - 1))`, scaled to log10 units. High values here indicate regions where the data itself is inherently noisy/variable — think of it as irreducible variability in the simulated field at that location [1].
> - **Epistemic uncertainty volume**: `sqrt(beta / (v * (alpha - 1)))`, scaled likewise. High values here indicate regions where the model is unsure due to sparse/limited training coverage — e.g., out-of-distribution regions or areas where different model fits would disagree [1].
> 
> Practically:
> - Bright/high regions in the **aleatoric** volume point to places where the underlying phenomenon is genuinely variable or hard to resolve numerically, and more model training won't fix it.
> - Bright/high regions in the **epistemic** volume point to places where the surrogate lacks sufficient data/knowledge — these are the regions where acquiring more simulation samples (or being cautious about extrapolation) would most improve confidence.
> - Both volumes share the same spatial domain as the prediction volume, so you can visually cross-reference: a region with high prediction but also high epistemic uncertainty warrants more caution than one with high aleatoric but low epistemic uncertainty (the latter is "confidently uncertain" due to data randomness, not model ignorance).
> 
> This decomposition has been validated on cases with known ground truth (e.g., the Lorenz-63 bifurcation, where aleatoric uncertainty rises sharply past the bifurcation point while epistemic uncertainty is reserved for genuinely out-of-distribution regions), showing the framework separates the two sources faithfully rather than conflating them [4].

**Retrieved sources shown to the user** (the References panel under the answer): `ParaSpace_View3_Documentation` ×3, `TVCG_Conformalized` ×2, `NeurIPS-2020-deep-evidential-regression-Paper`

---

### Q2 — Interface / workflow guidance

**Question.** How does Recommend Parameters work in the Para-space view?

*Live session state sent with the question: yes · response time 11.2 s · mode `llm`*

**Answer.**

> ## How "Recommend Parameters" Works in View 3
> 
> When you press **Recommend Parameters** in the Para-space View, the tool performs the following process:
> 
> 1. **Inputs you configure beforehand:**
>    - A **Context Field** (OmM/OmB/h parameters), loaded via "Load Field"
>    - A **Region of Interest (ROI)**, defined as voxel index ranges for X/Y/Z (shown as an orange wireframe box)
>    - A **Reference** target, chosen from: Pred, uncalibrated lower/upper bound, or conformally calibrated lower/upper bound — all evaluated at the Context Field's parameters and the currently selected confidence level
>    - Two **preference toggles** (Maximize/Minimize) for aleatoric (data) and epistemic (model) uncertainty [4]
> 
> 2. **Backend optimization:**
>    The backend runs **multi-start Adam gradient-based optimization** (activation maximization) directly on the evidential INR surrogate model. It searches parameter space for settings whose predicted output inside the ROI is closest — measured by **RMSE in log10 density space** — to the chosen Reference field.
> 
> 3. **Output — ranked candidates:**
>    Each candidate recommendation reports:
>    - Its parameter values
>    - RMSE vs. the reference
>    - ROI-mean aleatoric and epistemic uncertainty
> 
>    Candidates are then **re-ranked** according to your Maximize/Minimize preferences for data/model uncertainty [1].
> 
> 4. **Interacting with results:**
>    You can **Preview** a candidate to render its prediction/uncertainty triple, or **Send to View-1/2** to hand its parameters back to View 1/2, where they are auto-submitted as a new history record [3][4].
> 
> ### Notes on behavior (from the FAQ):
> - Because the feature-grid INR is piecewise-linear in the parameters, ROI objectives are often **monotone**, so optimal recommendations can sit on parameter range boundaries.
> - Multiple random starts may converge to near-identical optima; near-duplicates within 0.02 normalized distance are merged, though visually similar distinct optima can still appear.
> - Even when the reference is "Pred at the same parameters," RMSE won't be exactly zero for a top candidate, since the optimizer explores *other* parameter points and reports how close it can get.
> - The confidence slider **does** affect recommendations whenever the reference is an interval bound, since the bound value itself depends on the confidence (and, for calibrated bounds, the snapped calibration level) [2].
> 
> ### In your current state:
> - Reference is **Pred**, context params are OmM=0.14, OmB=0.0225, h=0.72, confidence=0.9.
> - The top-ranked candidate (rank 1) has parameters nearly identical to the context (0.140005, 0.0225004, 0.720008) with a very small RMSE (~1.8e-5), consistent with the FAQ explanation that even same-parameter-like matches won't hit exactly zero.
> - Your preferences are set to **maximize both aleatoric and epistemic uncertainty**, so the re-ranking favors candidates with higher ROI-mean uncertainty among those close to the reference.

**Retrieved sources shown to the user** (the References panel under the answer): `ParaSpace_View3_Documentation` ×4, `NNVA` ×2

---

### Q3 — Method grounding with citations

**Question.** Why do the calibrated intervals have a coverage guarantee, and what assumption does that rely on?

*Live session state sent with the question: no · response time 16.4 s · mode `llm`*

**Answer.**

> The coverage guarantee comes from the conformal calibration step applied on top of the evidential (student‑t) intervals. In this tool, for a chosen confidence level the raw predictive interval is first computed from the DER outputs (gamma, v, alpha, beta), giving quantiles q_lo/q_hi; the calibration step then forms **C = [q_lo − Q_lo, q_hi + Q_hi]**, where Q_lo and Q_hi are empirical quantiles of non‑conformity scores computed on a held‑out calibration set. This adjustment is what converts an otherwise heuristic, possibly miscalibrated interval into one with a formal coverage guarantee.
> 
> Why this works and what it relies on:
> 
> - The underlying evidential/quantile intervals are often uncalibrated and may not achieve the nominal coverage rate on their own [2]. Conformal prediction corrects this by using the calibration-set non-conformity scores to widen (or otherwise adjust) the interval so that it provably attains the desired coverage level, as shown by the close match to the ideal y = x coverage curve in the paper's evaluation [2].
> - This guarantee is a *finite-sample* one: methods built on conformal prediction (e.g., CQR) are explicitly shown to hit the nominal coverage (e.g., 90%) across many datasets/splits, unlike non-conformalized quantile methods, which can overcover or undercover unpredictably [3][6].
> - The reason the guarantee holds is that the calibration step uses a separate calibration set to compute quantiles of the model's non-conformity scores, and the theoretical proof for this construction requires only "minimal assumptions" on the data, rather than assumptions on the correctness of the underlying model itself [2]. The excerpts do not spell out the exact technical condition (exchangeability of calibration and test data) beyond describing it as "minimal assumptions" with "strict mathematical proofs" [2]; if you need the precise formal assumption (e.g., exchangeability), that level of detail is not present in the retrieved excerpts, so I can't state it with certainty from the provided sources.
> 
> In short: the guarantee is empirical-quantile-based (not just relying on model calibration), it needs a calibration dataset, and the papers describe it as valid under "minimal assumptions" — but the exact statistical assumption name isn't given in these excerpts [2][3][6].

**Retrieved sources shown to the user** (the References panel under the answer): `ParaSpace_View3_Documentation`, `TVCG_Conformalized` ×2, `Conformalized Quantile Regression` ×2, `NeurIPS-2020-deep-evidential-regression-Paper`

---

### Q4 — Answer conditioned on live session state

**Question.** Look at my current recommendations: is candidate #1 actually better than my current parameters, and why was it ranked first?

*Live session state sent with the question: yes · response time 34.7 s · mode `llm`*

**Answer.**

> **Is candidate #1 “better” than your current parameters?**
> 
> Not meaningfully — candidate #1's parameters (OmM≈0.140005, OmB≈0.0225004, h≈0.720008) are essentially identical to your current Context Field parameters (0.14, 0.0225, 0.72), differing only in the 5th–6th decimal. Its RMSE vs. the reference is 1.8×10⁻⁵, i.e. essentially zero in log10-density units, and its ROI-mean aleatoric/epistemic values (0.024418 / 0.010277) are virtually indistinguishable from your current evaluation (0.024419 / 0.010277). So candidate #1 is not a *different* useful operating point; it's the optimizer converging back onto (a point extremely close to) your starting parameters.
> 
> This matches the documented behavior: because your **Reference** is set to "pred" evaluated at the Context Field parameters themselves, the closest possible match to that reference is trivially the same point. The RMSE isn't exactly 0 only because gradient-based optimization from a different random start lands near, but not exactly on, that point — this is explicitly called out in the FAQ: *"Why is the RMSE not zero when the reference is Pred at the same parameters? … candidates are other parameter points, and the optimizer reports how close their prediction can get inside the ROI"* [1].
> 
> **Why was it ranked first?**
> 
> The recommendation list is generated by minimizing RMSE vs. the reference (the "match" objective) via multi-start Adam optimization, then the resulting near-optimal candidates are re-ranked according to your uncertainty preferences (currently both aleatoric and epistemic set to "Maximize") using min-max normalized scores summed and sorted [2][3].
> 
> Looking at the actual numbers you have, the six candidates are listed in strictly increasing RMSE order (1.8e-5 → 0.0024 → 0.0026 → 0.0033 → 0.0035 → 0.0052), which is exactly the ordering you'd get by ranking on RMSE alone. If the "Maximize aleatoric / Maximize epistemic" preference had been applied on top (per the min-max normalize-and-sum rule in [3]), candidate #4 — which has the *highest* aleatoric (0.024861) and epistemic (0.010484) among the six — would score highest and should appear on top instead of #1, with #1 (which has the *second-lowest* aleatoric/epistemic in the set) scoring near the bottom.
> 
> So the ranking you're seeing appears to reflect the raw RMSE-to-reference ordering rather than a preference-adjusted resort. I can't fully explain this discrepancy from the documentation alone (it may simply mean the preference toggle hasn't been re-applied/re-sorted for this list yet); the references don't give more detail on when re-sorting is triggered, so I won't speculate further. If you want candidates that actually maximize aleatoric/epistemic uncertainty, you may need to re-toggle the Maximize switches to force the re-sort, or manually compare the aleatoric/epistemic columns — based on those values, candidate #4 (and then #5) look like the better matches for a "maximize uncertainty" goal, not #1 [2][3].

**Retrieved sources shown to the user** (the References panel under the answer): `ParaSpace_View3_Documentation` ×3, `NNVA` ×2, `Surroflow`

---

### Q5 — Answer conditioned on live session state

**Question.** In my current ROI, which simulation parameter has the strongest influence on the prediction?

*Live session state sent with the question: yes · response time 4.7 s · mode `llm`*

**Answer.**

> Based on the parameter sensitivity metadata for your current ROI (mean |d(ROI-mean prediction)/d(normalized parameter)| computed via autograd on the surrogate), **h (Hubble parameter)** has the strongest influence on the prediction, with a sensitivity of ≈0.184 — noticeably higher than OmB (≈0.117) and OmM (≈0.091) [1].
> 
> This ranking (h > OmB > OmM) is consistent with your recommended parameter sets: across the top candidates, h shows the largest relative shifts from the context value (0.72), while OmM and OmB stay closer to their context values, reflecting that small changes in h have a proportionally larger effect on matching the reference prediction inside the ROI.

**Retrieved sources shown to the user** (the References panel under the answer): `ParaSpace_View3_Documentation` ×5, `Surroflow`

---

### Q6 — Out-of-scope probe (must refuse)

**Question.** What was the CPU wall-clock time of the original Nyx simulation for ensemble member 293?

*Live session state sent with the question: yes · response time 2.3 s · mode `llm`*

**Answer.**

> I don't have any information in the provided references or application state about per-member simulation wall-clock times for the Nyx ensemble (e.g., a specific "ensemble member 293"). The excerpts mention only general model training/test times and calibration times [1][3][6], and a runtime figure for a different (NNVA) simulation, not Nyx [2][5]. I cannot answer this question without fabricating data.

**Retrieved sources shown to the user** (the References panel under the answer): `Surroflow` ×2, `NNVA` ×2, `TVCG_Conformalized`, `ParaSpace_View3_Documentation`

---

## How to reproduce

With the repository set up (see the README) and an LLM key configured in `backend/ai_config.json`, `POST /ai/chat` with `{"messages": [...], "app_state": {...}}` returns `{answer, sources, provider, mode}`. `GET /ai/status` reports the knowledge-base size and the configured provider. Without a key the assistant does not fail and does not invent an answer: it falls back to a retrieval-only mode that returns the matching excerpts verbatim.

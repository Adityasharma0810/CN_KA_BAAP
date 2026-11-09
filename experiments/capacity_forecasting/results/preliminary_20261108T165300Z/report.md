# Preliminary capacity forecasting evaluation

Offline research result; not production-ready and not integrated into the live controller.

## Dataset and split

- Integrity-valid CSV/manifest pairs: **10**
- Training runs: 6
- Validation runs: 2
- Test runs: 2
- Excluded CSV files: 1
- Target: configured shared root-TBF capacity (Mbps), never observed throughput.
- Target matching uses actual timestamps and real observations only; no interpolation or synthetic samples.

### Run IDs

- Train: `b7f3620d-30ca-4835-b25c-8e5e9208d9e4, f653c1c1-9b6c-441c-b9e7-d08092dcf3a0, 77c12eef-c137-4c2d-bd0c-2e01c9ce199f, 667462a6-16e8-47b9-ba71-3f54ec79c2f7, 53bb4605-3607-4552-a3d2-b737ade0ca3e, 1833b84c-d80a-4278-94de-8d0d3488c8f8`
- Validation: `cf0a6412-7054-4b12-939c-f87287768fb6, 034ee0c3-6399-4f8c-941e-d24f668a5f7b`
- Test: `50d87c8c-fab8-4c95-b09d-e84581b4baeb, ab80352c-146f-493c-b55a-9429dd830c96`

### Exclusions

- `capacity_7613a820-508e-46cf-bcc5-9845e6557b25.csv`: /home/vboxuser/Projects/CN_KA_BAAP/data/capacity_forecasting/raw/capacity_7613a820-508e-46cf-bcc5-9845e6557b25.csv:2: row run_id '53664996-46d3-4ffe-967b-723cd6714426' does not match CSV filename run_id '7613a820-508e-46cf-bcc5-9845e6557b25'

## Validation-selected configurations

- Seasonal-naive period: **60 seconds**
- Seasonal-naive candidate scores: `[{"count": 118, "mae": 55.42372881355932, "season_seconds": 20.0}, {"count": 135, "mae": 36.888888888888886, "season_seconds": 30.0}, {"count": 89, "mae": 4.719101123595506, "season_seconds": 40.0}, {"count": 6, "mae": 0.0, "season_seconds": 60.0}]`
- Holt-Winters: season length 20 samples; selected smoothing `{"alpha": 0.5, "beta": 0.1, "gamma": 0.1}`
- Holt-Winters validation candidates: `[{"config": {"alpha": 0.2, "beta": 0.05, "gamma": 0.05}, "count": 9, "mae": 41.14394416002401}, {"config": {"alpha": 0.3, "beta": 0.1, "gamma": 0.1}, "count": 9, "mae": 51.829658669084765}, {"config": {"alpha": 0.5, "beta": 0.1, "gamma": 0.1}, "count": 9, "mae": 38.59283717797844}]`
- Holt-Winters training-only contiguous states persisted: **3**
- LightGBM: **not installed; not trained**

## Test metrics

| Scenario | Model | Horizon (s) | Pairs | MAE | RMSE | Bias | Improvement vs persistence | Changed pairs | Direction accuracy | Mean change lead (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| periodic | persistence | 5 | 79 | 16.2025 | 25.4578 | -4.0506 | 0.0000 | 32 | 0.0000 | 2.9542 |
| all | persistence | 5 | 79 | 16.2025 | 25.4578 | -4.0506 | 0.0000 | 32 | 0.0000 | 2.9542 |
| periodic | persistence | 10 | 66 | 35.7576 | 37.8193 | -10.3030 | 0.0000 | 59 | 0.0000 | 5.3775 |
| all | persistence | 10 | 66 | 35.7576 | 37.8193 | -10.3030 | 0.0000 | 59 | 0.0000 | 5.3775 |
| periodic | persistence | 30 | 37 | 35.6757 | 37.7760 | -20.5405 | 0.0000 | 33 | 0.0000 | 5.7431 |
| all | persistence | 30 | 37 | 35.6757 | 37.7760 | -20.5405 | 0.0000 | 33 | 0.0000 | 5.7431 |
| periodic | seasonal_naive | 5 | 1 | 40.0000 | 40.0000 | -40.0000 | — | 0 | — | — |
| all | seasonal_naive | 5 | 1 | 40.0000 | 40.0000 | -40.0000 | — | 0 | — | — |
| periodic | seasonal_naive | 10 | 0 | — | — | — | — | 0 | — | — |
| all | seasonal_naive | 10 | 0 | — | — | — | — | 0 | — | — |
| periodic | seasonal_naive | 30 | 0 | — | — | — | — | 0 | — | — |
| all | seasonal_naive | 30 | 0 | — | — | — | — | 0 | — | — |
| periodic | holt_winters | 5 | 0 | — | — | — | — | 0 | — | — |
| all | holt_winters | 5 | 0 | — | — | — | — | 0 | — | — |
| periodic | holt_winters | 10 | 0 | — | — | — | — | 0 | — | — |
| all | holt_winters | 10 | 0 | — | — | — | — | 0 | — | — |
| periodic | holt_winters | 30 | 0 | — | — | — | — | 0 | — | — |
| all | holt_winters | 30 | 0 | — | — | — | — | 0 | — | — |
| periodic | lightgbm | 5 | 0 | — | — | — | — | 0 | — | — |
| all | lightgbm | 5 | 0 | — | — | — | — | 0 | — | — |
| periodic | lightgbm | 10 | 0 | — | — | — | — | 0 | — | — |
| all | lightgbm | 10 | 0 | — | — | — | — | 0 | — | — |
| periodic | lightgbm | 30 | 0 | — | — | — | — | 0 | — | — |
| all | lightgbm | 30 | 0 | — | — | — | — | 0 | — | — |

Validation metrics are recorded in `metrics.csv` and were used only to select seasonal period and Holt-Winters smoothing configuration. Test metrics were computed after selection.

## Direction and timing

Capacity-change direction is assessed only for target pairs whose configured capacity differs from the origin. Mean change lead is the measured time from forecast origin to the first observed capacity transition within the target interval. A scripted schedule is known to the experimenter but is not supplied as a model feature; an unannounced abrupt change cannot be predicted from history alone unless its precursor is observable.

## Leakage controls

- Files are independently loaded through the manifest-aware schema validator; malformed/mismatched runs are excluded.
- Run IDs are assigned chronologically to disjoint 6/2/2 train/validation/test groups before target construction.
- Targets use only configured TBF labels at future timestamps in the same run; throughput is never used as target.
- Persistence and seasonal-naive use only capacity observations at or before each origin.
- Holt-Winters smoothing configuration is selected on validation. Its per-origin filter state uses only the contiguous, cadence-valid history through that origin; forecasts are omitted when that history is insufficient.
- LightGBM is not trained when its optional dependency is absent.

## Limitations and recommendations

- The test split contains only periodic runs; the validation split contains only step runs. This is a run-disjoint chronological evaluation, not broad scenario-generalization evidence.
- Cadence-invalid intervals are preserved but cannot be used to form regular Holt-Winters history. No samples are inserted to repair gaps.
- The experiment uses scripted, repeating TBF settings. Performance does not demonstrate prediction of genuinely unexpected ISP capacity changes.
- Test results are based on only two independent runs and short 60-second traces.
- LightGBM remains unavailable in the selected `.venv`; no dependency was installed.
- Collect more independently seeded runs, including held-out transition timings/periods and additional scenario families, before stronger model claims.

## Artifacts

- Predictions: `predictions.csv`
- Metrics: `metrics.csv`
- Actual-vs-predicted plots:
  - `actual_vs_predicted_50d87c8c_5s.svg`
  - `actual_vs_predicted_50d87c8c_10s.svg`
  - `actual_vs_predicted_50d87c8c_30s.svg`
  - `actual_vs_predicted_ab80352c_5s.svg`
  - `actual_vs_predicted_ab80352c_10s.svg`
  - `actual_vs_predicted_ab80352c_30s.svg`

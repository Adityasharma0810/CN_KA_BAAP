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
- LightGBM selected configurations by horizon: `{"5": {"learning_rate": 0.05, "max_depth": 3, "min_data_in_leaf": 5, "n_estimators": 100, "num_leaves": 7, "num_threads": 1, "objective": "regression", "seed": 20261108, "verbosity": -1}, "10": {"learning_rate": 0.05, "max_depth": 3, "min_data_in_leaf": 5, "n_estimators": 100, "num_leaves": 7, "num_threads": 1, "objective": "regression", "seed": 20261108, "verbosity": -1}, "30": {"learning_rate": 0.05, "max_depth": 3, "min_data_in_leaf": 5, "n_estimators": 50, "num_leaves": 7, "num_threads": 1, "objective": "regression", "seed": 20261108, "verbosity": -1}}`
- LightGBM validation candidate scores: `{"5": [{"count": 89, "mae": 13.089025582513795, "n_estimators": 20}, {"count": 89, "mae": 9.966242870723885, "n_estimators": 50}, {"count": 89, "mae": 9.22636932079914, "n_estimators": 100}], "10": [{"count": 80, "mae": 16.090352798218095, "n_estimators": 20}, {"count": 80, "mae": 12.44960869891145, "n_estimators": 50}, {"count": 80, "mae": 11.395529140708359, "n_estimators": 100}], "30": [{"count": 49, "mae": 11.594036001222282, "n_estimators": 20}, {"count": 49, "mae": 10.654143308430374, "n_estimators": 50}, {"count": 49, "mae": 10.945954081499593, "n_estimators": 100}]}`

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
| periodic | lightgbm | 5 | 79 | 17.8085 | 20.3783 | -8.5081 | -0.0991 | 32 | 0.9375 | 2.9542 |
| all | lightgbm | 5 | 79 | 17.8085 | 20.3783 | -8.5081 | -0.0991 | 32 | 0.9375 | 2.9542 |
| periodic | lightgbm | 10 | 66 | 10.8060 | 13.0209 | -3.6845 | 0.6978 | 59 | 1.0000 | 5.3775 |
| all | lightgbm | 10 | 66 | 10.8060 | 13.0209 | -3.6845 | 0.6978 | 59 | 1.0000 | 5.3775 |
| periodic | lightgbm | 30 | 37 | 11.5535 | 12.9200 | -6.3127 | 0.6762 | 33 | 1.0000 | 5.7431 |
| all | lightgbm | 30 | 37 | 11.5535 | 12.9200 | -6.3127 | 0.6762 | 33 | 1.0000 | 5.7431 |

## Validation metrics

| Scenario | Model | Horizon (s) | Pairs | MAE | RMSE | Bias | Improvement vs persistence | Changed pairs | Direction accuracy | Mean change lead (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| step | persistence | 5 | 89 | 10.7865 | 25.4399 | 1.3483 | 0.0000 | 16 | 0.0000 | 2.8424 |
| all | persistence | 5 | 89 | 10.7865 | 25.4399 | 1.3483 | 0.0000 | 16 | 0.0000 | 2.8424 |
| step | persistence | 10 | 80 | 24.0000 | 37.9473 | -1.5000 | 0.0000 | 32 | 0.0000 | 5.0867 |
| all | persistence | 10 | 80 | 24.0000 | 37.9473 | -1.5000 | 0.0000 | 32 | 0.0000 | 5.0867 |
| step | persistence | 30 | 49 | 36.7347 | 46.9476 | -9.7959 | 0.0000 | 30 | 0.0000 | 14.7830 |
| all | persistence | 30 | 49 | 36.7347 | 46.9476 | -9.7959 | 0.0000 | 30 | 0.0000 | 14.7830 |
| step | seasonal_naive | 5 | 2 | 0.0000 | 0.0000 | 0.0000 | — | 0 | — | — |
| all | seasonal_naive | 5 | 2 | 0.0000 | 0.0000 | 0.0000 | — | 0 | — | — |
| step | seasonal_naive | 10 | 2 | 0.0000 | 0.0000 | 0.0000 | — | 0 | — | — |
| all | seasonal_naive | 10 | 2 | 0.0000 | 0.0000 | 0.0000 | — | 0 | — | — |
| step | seasonal_naive | 30 | 2 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 2 | 1.0000 | 8.5458 |
| all | seasonal_naive | 30 | 2 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 2 | 1.0000 | 8.5458 |
| step | holt_winters | 5 | 7 | 40.2793 | 51.0288 | -0.1147 | — | 0 | — | — |
| all | holt_winters | 5 | 7 | 40.2793 | 51.0288 | -0.1147 | — | 0 | — | — |
| step | holt_winters | 10 | 2 | 32.6903 | 38.0332 | 19.4388 | — | 0 | — | — |
| all | holt_winters | 10 | 2 | 32.6903 | 38.0332 | 19.4388 | — | 0 | — | — |
| step | holt_winters | 30 | 0 | — | — | — | — | 0 | — | — |
| all | holt_winters | 30 | 0 | — | — | — | — | 0 | — | — |
| step | lightgbm | 5 | 89 | 9.2264 | 17.9423 | 5.7246 | 0.1446 | 16 | 0.9375 | 2.8424 |
| all | lightgbm | 5 | 89 | 9.2264 | 17.9423 | 5.7246 | 0.1446 | 16 | 0.9375 | 2.8424 |
| step | lightgbm | 10 | 80 | 11.3955 | 18.7505 | 7.4808 | 0.5252 | 32 | 1.0000 | 5.0867 |
| all | lightgbm | 10 | 80 | 11.3955 | 18.7505 | 7.4808 | 0.5252 | 32 | 1.0000 | 5.0867 |
| step | lightgbm | 30 | 49 | 10.6541 | 19.6590 | 7.8993 | 0.7100 | 30 | 1.0000 | 14.7830 |
| all | lightgbm | 30 | 49 | 10.6541 | 19.6590 | 7.8993 | 0.7100 | 30 | 1.0000 | 14.7830 |

Validation metrics were used to select Holt-Winters smoothing. Seasonal-naive period was selected by validation MAE, but the selected 60-second period had only six validation forecasts; treat its test result as low-coverage and preliminary. Test metrics were computed after configuration selection and are listed in the preceding table. The test data was also inspected in a prior post-hoc seasonal-naive diagnostic, so this is exploratory rather than an untouched final test.

## Direction and timing

Capacity-change direction is assessed only for target pairs whose configured capacity differs from the origin. Mean change lead is the measured time from forecast origin to the first observed capacity transition within the target interval. A scripted schedule is known to the experimenter but is not supplied as a model feature; an unannounced abrupt change cannot be predicted from history alone unless its precursor is observable.

## Leakage controls

- Files are independently loaded through the manifest-aware schema validator; malformed/mismatched runs are excluded.
- Run IDs are assigned chronologically to disjoint 6/2/2 train/validation/test groups before target construction.
- Targets use only configured TBF labels at future timestamps in the same run; throughput is never used as target.
- Persistence and seasonal-naive use only capacity observations at or before each origin.
- Holt-Winters smoothing configuration is selected on validation. Its per-origin filter state uses only the contiguous, cadence-valid history through that origin; forecasts are omitted when that history is insufficient.
- LightGBM regressors are fit only on training-run examples; estimator count is selected on validation for each horizon.

## Limitations and recommendations

- The test runs were inspected in a post-hoc seasonal-naive diagnostic before this evaluation. Do not treat these metrics as a pristine final holdout; collect fresh independent test runs for final claims.
- The test split contains only periodic runs; the validation split contains only step runs. This is a run-disjoint chronological evaluation, not broad scenario-generalization evidence.
- Cadence-invalid intervals are preserved but cannot be used to form regular Holt-Winters history. No samples are inserted to repair gaps.
- The test runs have fewer than the 40 contiguous samples required to initialize Holt-Winters with a 20-sample seasonal period, so it has no test forecasts or test metrics.
- The experiment uses scripted, repeating TBF settings. Performance does not demonstrate prediction of genuinely unexpected ISP capacity changes.
- Test results are based on only two independent runs and short 60-second traces.
- LightGBM was installed in the selected `.venv` for this approved offline evaluation.
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

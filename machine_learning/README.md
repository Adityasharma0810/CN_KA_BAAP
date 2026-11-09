# Experience Budget — Machine Learning Modules

This directory contains the machine learning models, training notebooks, and evaluation documentation for the **Experience Budget** network traffic analysis subsystem.

> [!WARNING]
> **Independent Validation Notice:** Neither model has been validated on independent, real-world traffic capture sessions. The reported evaluation metrics reflect offline benchmarks on the ISCX VPN-nonVPN dataset (Scenarios A1 and A2). Real-world generalization, cross-session drift, and network conditions remain to be validated.

---

## Directory Structure

```text
machine_learning/
├── notebooks/
│   └── Experience_Budget_ML.ipynb             # Google Colab Jupyter training & evaluation notebook
├── saved_models/
│   ├── vpn_classifier_random_forest.joblib    # Trained Random Forest model (VPN vs Non-VPN)
│   └── application_classifier_xgboost.joblib  # Trained XGBoost model (7-class Application)
├── datasets/                                  # Reserved for ARFF datasets (kept empty / uncommitted)
├── evaluation/                                # Reserved for evaluation artifacts, confusion matrices & plots
└── README.md                                  # ML subsystem specification and benchmark reports
```

---

## 1. VPN vs. Non-VPN Classifier

- **Model Type:** Random Forest Pipeline (`SimpleImputer(strategy="median")` + `RandomForestClassifier`)
- **Task:** Binary network traffic classification (VPN tunnel detection)
- **Time Window:** 15 seconds (time-based flow statistics)
- **Target Output Labels:**
  - `0`: `NON-VPN`
  - `1`: `VPN`

### Input Features (23 time-based statistical features)

The model accepts 23 continuous features derived from 15-second bidirectional flow statistics:

| # | Feature Name | Description |
|---|---|---|
| 1 | `duration` | Total duration of the network flow |
| 2 | `total_fiat` | Total forward inter-arrival time |
| 3 | `total_biat` | Total backward inter-arrival time |
| 4 | `min_fiat` | Minimum forward inter-arrival time |
| 5 | `min_biat` | Minimum backward inter-arrival time |
| 6 | `max_fiat` | Maximum forward inter-arrival time |
| 7 | `max_biat` | Maximum backward inter-arrival time |
| 8 | `mean_fiat` | Mean forward inter-arrival time |
| 9 | `mean_biat` | Mean backward inter-arrival time |
| 10 | `flowPktsPerSecond` | Packet rate (packets/second) |
| 11 | `flowBytesPerSecond` | Byte throughput (bytes/second) |
| 12 | `min_flowiat` | Minimum packet inter-arrival time for the flow |
| 13 | `max_flowiat` | Maximum packet inter-arrival time for the flow |
| 14 | `mean_flowiat` | Mean packet inter-arrival time for the flow |
| 15 | `std_flowiat` | Standard deviation of flow inter-arrival times |
| 16 | `min_active` | Minimum active duration before flow idles |
| 17 | `mean_active` | Mean active duration |
| 18 | `max_active` | Maximum active duration |
| 19 | `std_active` | Standard deviation of active periods |
| 20 | `min_idle` | Minimum idle time between bursts |
| 21 | `mean_idle` | Mean idle duration |
| 22 | `max_idle` | Maximum idle duration |
| 23 | `std_idle` | Standard deviation of idle periods |

### Benchmark Evaluation

- **Evaluation Protocol:** Trained on Scenario A1 (15-second window), evaluated cross-scenario on Scenario A2 (18,758 samples).
- **Observed Metrics:**
  - **Accuracy:** ~`75.96%` (0.7596)
  - **VPN F1-Score:** `77.36%` (0.7736)
  - **Macro Average F1:** `76.0%`
  - **Detailed Classification Breakdown:**
    - `Non-VPN`: Precision `0.76`, Recall `0.73`, F1 `0.74` (support: 8,965)
    - `VPN`: Precision `0.76`, Recall `0.79`, F1 `0.77` (support: 9,793)

---

## 2. Seven-Class Application Classifier

- **Model Type:** XGBoost Pipeline (`SimpleImputer(strategy="median")` + `XGBClassifier`)
  - Parameters: `n_estimators=200`, `max_depth=5`, `learning_rate=0.1`, `tree_method="hist"`, `eval_metric="mlogloss"`
- **Task:** Multi-class application intent classification
- **Time Window:** 15 seconds
- **Target Output Labels (7 classes):**
  1. `BROWSING` (Web browsing)
  2. `CHAT` (Instant messaging)
  3. `FT` (File Transfer)
  4. `MAIL` (Email synchronization)
  5. `P2P` (Peer-to-Peer file sharing)
  6. `STREAMING` (Video/audio streaming)
  7. `VOIP` (Voice over IP)

### Input Features

Uses the same 23 time-based statistical features listed above.

### Benchmark Evaluation

- **Evaluation Protocol:** Stratified random 80/20 train/test split on Scenario A2 (15,006 train rows, 3,752 test rows).
- **Observed Metrics:**
  - **Accuracy:** `90.27%` (0.9027)
  - **Macro F1-Score:** `87.61%` (0.8761)
  - **Weighted F1-Score:** `90.21%`
  - **Detailed Classification Breakdown:**
    - `BROWSING`: Precision `0.90`, Recall `0.95`, F1 `0.92` (support: 1,000)
    - `CHAT`: Precision `0.85`, Recall `0.74`, F1 `0.79` (support: 417)
    - `FT`: Precision `0.86`, Recall `0.82`, F1 `0.84` (support: 590)
    - `MAIL`: Precision `0.83`, Recall `0.94`, F1 `0.88` (support: 148)
    - `P2P`: Precision `0.83`, Recall `0.93`, F1 `0.88` (support: 386)
    - `STREAMING`: Precision `0.89`, Recall `0.79`, F1 `0.83` (support: 191)
    - `VOIP`: Precision `1.00`, Recall `0.98`, F1 `0.99` (support: 1,020)

---

## 3. Important Methodological Notes & Limitations

1. **Independent Session Validation:** Neither model has been validated on distinct, live packet captures outside the benchmark dataset. Cross-scenario evaluation drops binary VPN performance to ~76%, showing feature sensitivity across network environments.
2. **Window-Level Correlation:** The 90.27% accuracy on application classification was measured on a random test split of 15-second windows. Windows originating from the same traffic flows are correlated; session-level holdouts are recommended before production deployment.
3. **Deployment Status:** This directory is currently strictly isolated. No models are linked to the FastAPI backend, network telemetry monitors, or React frontend.


# QoE proxy formulas

These deterministic scores are transparent operational proxies, not
standardized MOS (Mean Opinion Score) and not a trained classifier. The only
class source is the profile explicitly declared by an active Scenario Lab run.
Without that mapping, the class and score are unknown. All inputs come from
stored observations; null required inputs always yield an unknown score.

Scores are clamped to 0–100. Bands are green at 75–100, amber at 50–74.99,
and red below 50.

## Call

This simplified E-model-style proxy estimates one-way delay as `RTT / 2`:

```text
score = clamp(100 - 0.5 * (RTT_ms / 2)
                  - 1.5 * RTT_variation_ms
                  - 2.5 * ICMP_loss_percent)
```

RTT, RTT variation, and ICMP packet loss are all required. The ICMP loss
measurement is a network-layer indicator, not application loss.

## Game

```text
score = clamp(100 - 0.8 * RTT_ms - 2.0 * RTT_variation_ms)
```

RTT and RTT variation are both required.

## Stream

The target steady bitrate is 8 Mbit/s. Let `CV` be the population standard
deviation divided by the mean of the last five valid stored client download
rates:

```text
score = clamp(100 * min(1, download_Mbps / 8) * (1 - min(1, CV)))
```

The current download rate and five valid rate samples are required. The ratio
is treated as zero when all five measured rates are zero; measured zero is
different from null.

## Bulk

The measured aggregate Linux-gateway download rate is used as the observed
capacity proxy. The max-min fair share is that measured capacity divided by
the number of concurrently declared scenario flows:

```text
fair_share_Mbps = aggregate_download_Mbps / active_flow_count
score = clamp(100 * min(1, client_download_Mbps / fair_share_Mbps))
```

Client rate, positive aggregate capacity, and active flow count are required.
This intentionally evaluates the observed share against contemporaneous
measured capacity; it does not claim to estimate the physical link's nominal
capacity.

## Missing values and provenance

Each class returns `unknown` when any required measurement or sample window is
missing. Zero is scored as a measured value and is never substituted for null.
The API lists the inputs, units, observed timestamps, and missing input names.
No classifier in `machine_learning/` is connected to this scorecard.

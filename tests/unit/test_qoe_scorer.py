from types import SimpleNamespace

import pytest

from ml.qoe.scorer import score_qoe


def observation(**values):
    defaults = {
        "rtt_ms": None,
        "rtt_variation_ms": None,
        "packet_loss_percent": None,
        "download_mbps": None,
    }
    return SimpleNamespace(**(defaults | values))


@pytest.mark.parametrize(
    ("traffic_class", "required"),
    [
        ("call", ("rtt_ms", "rtt_variation_ms", "packet_loss_percent")),
        ("game", ("rtt_ms", "rtt_variation_ms")),
        ("stream", ("download_mbps",)),
        ("bulk", ("download_mbps",)),
    ],
)
def test_missing_required_inputs_return_unknown(traffic_class, required):
    result = score_qoe(traffic_class, observation())

    assert result.score is None
    assert result.band == "unknown"
    assert set(required).issubset(result.missing_inputs)


def test_call_proxy_boundaries_and_loss_extremes():
    best = score_qoe(
        "call",
        observation(rtt_ms=0, rtt_variation_ms=0, packet_loss_percent=0),
    )
    worst = score_qoe(
        "call",
        observation(rtt_ms=1000, rtt_variation_ms=1000, packet_loss_percent=100),
    )

    assert (best.score, best.band) == (100, "green")
    assert (worst.score, worst.band) == (0, "red")


def test_game_proxy_clamps_extreme_latency_and_variation():
    result = score_qoe(
        "game",
        observation(rtt_ms=1000, rtt_variation_ms=1000),
    )

    assert result.score == 0
    assert result.band == "red"


def test_stream_requires_five_rates_and_scores_measured_zero_as_zero():
    stable_zero = [observation(download_mbps=0) for _ in range(5)]
    measured = score_qoe(
        "stream",
        stable_zero[0],
        history=stable_zero,
    )
    insufficient = score_qoe(
        "stream",
        observation(download_mbps=0),
        history=[observation(download_mbps=0)],
    )

    assert measured.score == 0
    assert measured.band == "red"
    assert insufficient.score is None
    assert "rate_stability_samples" in insufficient.missing_inputs


def test_stream_null_in_stability_window_makes_score_unknown():
    samples = [observation(download_mbps=8) for _ in range(4)]
    samples.insert(2, observation(download_mbps=None))
    result = score_qoe(
        "stream",
        observation(download_mbps=8),
        history=samples,
    )

    assert result.score is None
    assert result.band == "unknown"
    assert "rate_stability_samples" in result.missing_inputs


def test_stream_stability_penalty_uses_last_five_samples():
    samples = [observation(download_mbps=8) for _ in range(5)]
    stable = score_qoe("stream", samples[0], history=samples)
    unstable = score_qoe(
        "stream",
        samples[0],
        history=[
            observation(download_mbps=0),
            observation(download_mbps=16),
            observation(download_mbps=0),
            observation(download_mbps=16),
            observation(download_mbps=8),
        ],
    )

    assert stable.score == 100
    assert unstable.score < stable.score


def test_bulk_scores_relative_to_measured_fair_share():
    zero = score_qoe(
        "bulk",
        observation(download_mbps=0),
        measured_capacity_mbps=12,
        fair_share_clients=3,
    )
    fair_share = score_qoe(
        "bulk",
        observation(download_mbps=4),
        measured_capacity_mbps=12,
        fair_share_clients=3,
    )
    no_capacity = score_qoe(
        "bulk",
        observation(download_mbps=4),
        measured_capacity_mbps=0,
        fair_share_clients=3,
    )

    assert zero.score == 0
    assert fair_share.score == 100
    assert no_capacity.score is None
    assert "measured_capacity_mbps" in no_capacity.missing_inputs


def test_unknown_class_never_claims_a_score():
    result = score_qoe("unknown", observation(download_mbps=100))

    assert result.score is None
    assert result.band == "unknown"
    assert result.missing_inputs == ("traffic_class",)

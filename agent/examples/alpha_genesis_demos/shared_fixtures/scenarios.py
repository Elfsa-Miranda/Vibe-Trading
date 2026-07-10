from __future__ import annotations


QUALITY_SCENARIOS = {
    "future_leak_trap": {
        "formula": "rank(future_return)",
        "execution_return_mean": 0.04,
        "turnover_mean": 0.20,
        "trial_count": 1,
    },
    "cherry_picked_noise_trap": {
        "formula": "rank(noise_candidate_073)",
        "execution_return_mean": 0.005,
        "turnover_mean": 0.40,
        "trial_count": 100,
        "selected_p_value": 0.001,
    },
    "survivorship_bias_trap": {
        "formula": "rank(close)",
        "execution_return_mean": 0.02,
        "turnover_mean": 0.30,
        "trial_count": 4,
        "survivorship_bias": True,
    },
    "high_turnover_cost_trap": {
        "formula": "rank(intraday_noise_proxy)",
        "execution_return_mean": -0.01,
        "turnover_mean": 80.0,
        "cost_bps_mean": 120.0,
        "trial_count": 8,
    },
    "duplicate_public_alpha_trap": {
        "formula": "rank(public_alpha101_001_clone)",
        "execution_return_mean": 0.03,
        "turnover_mean": 0.25,
        "trial_count": 3,
        "duplicate_alpha": True,
    },
    "orthogonal_liquidity_reversal_candidate": {
        "formula": "rank(group_neutralize(mul(neg(ret_5d), volume_shock(amount, 20)), industry))",
        "execution_return_mean": 0.012,
        "turnover_mean": 0.35,
        "rank_ic_mean": 0.02,
        "rank_icir": 0.5,
        "t_stat": 1.5,
        "mean_coverage": 0.25,
        "trial_count": 12,
        "orthogonal_synergy": True,
    },
}

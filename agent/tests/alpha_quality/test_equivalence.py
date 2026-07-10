from src.alpha_quality.falsification.equivalence import tost, tost_from_summary


def test_non_significant_difference_does_not_prove_equivalence() -> None:
    assert not tost(lower_p=.2, upper_p=.2, alpha=.05, effective_n=100, min_effective_n=10).equivalent
    wide = tost_from_summary(estimate=0.0, standard_error=1.0, margin=0.1, alpha=.05, effective_n=100, minimum_effective_n=10)
    assert not wide.equivalent


def test_tost_requires_both_one_sided_tests_at_allocated_alpha() -> None:
    assert tost(lower_p=.01, upper_p=.01, alpha=.05, effective_n=10, min_effective_n=10).equivalent
    assert not tost(lower_p=.01, upper_p=.2, alpha=.05, effective_n=10, min_effective_n=10).equivalent


def test_tost_intersection_union_is_one_registered_family_member() -> None:
    result = tost_from_summary(estimate=0.01, standard_error=0.01, margin=0.05, alpha=.05, effective_n=100, minimum_effective_n=20)
    assert result.equivalent
    assert result.lower_p_value <= .05 and result.upper_p_value <= .05

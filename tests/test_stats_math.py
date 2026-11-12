import math

import pytest

from landing_page_lab.stats._math import chi2_sf, gamma_q, norm_cdf, norm_ppf, norm_sf


@pytest.mark.parametrize("x,df,p", [(3.841458820694124, 1, 0.05), (5.991464547107979, 2, 0.05),
                                    (9.21034037197618, 2, 0.01), (13.815510557964274, 2, 0.001),
                                    (16.918977604620448, 9, 0.05), (0.0, 3, 1.0)])
def test_chi2_sf_matches_tables(x, df, p):
    assert chi2_sf(x, df) == pytest.approx(p, rel=1e-8)


def test_gamma_q_both_branches_agree_with_closed_form():
    # Q(1, x) = exp(-x) exercises the series (x < 2) and continued fraction (x >= 2) paths.
    for x in (0.1, 1.5, 2.5, 10.0, 40.0):
        assert gamma_q(1.0, x) == pytest.approx(math.exp(-x), rel=1e-10)


def test_normal_helpers():
    assert norm_cdf(1.959963984540054) == pytest.approx(0.975, abs=1e-12)
    assert norm_ppf(0.975) == pytest.approx(1.959963984540054, abs=1e-9)
    assert norm_sf(8.0) == pytest.approx(6.22096057427e-16, rel=1e-6)  # no cancellation in the far tail
    with pytest.raises(ValueError):
        norm_ppf(1.0)

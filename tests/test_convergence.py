from data_layer.convergence import check_convergence


def test_stable_metric_reports_stable():
    def analysis_fn(size):
        return {"p_home_to_news": 0.50 + 0.001 * (size == 5)}

    report = check_convergence(analysis_fn, sizes=[1, 5, 10], tol=0.05)
    assert report["stable"] is True
    assert len(report["results"]) == 3


def test_unstable_metric_reports_unstable():
    def analysis_fn(size):
        return {"m": float(size)}

    report = check_convergence(analysis_fn, sizes=[1, 10, 100], tol=0.05)
    assert report["stable"] is False
    assert report["max_change"] > 0.05

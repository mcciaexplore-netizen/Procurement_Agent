from app.operational import SlidingWindowRateLimiter


def test_sliding_window_rate_limiter_expires_old_requests() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)

    assert limiter.allow("buyer", now=0)
    assert limiter.allow("buyer", now=1)
    assert not limiter.allow("buyer", now=2)
    assert limiter.allow("buyer", now=10)

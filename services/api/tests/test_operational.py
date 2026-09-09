from app.operational import SlidingWindowRateLimiter, configured_origins


def test_sliding_window_rate_limiter_expires_old_requests() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)

    assert limiter.allow("buyer", now=0)
    assert limiter.allow("buyer", now=1)
    assert not limiter.allow("buyer", now=2)
    assert limiter.allow("buyer", now=10)


def test_configured_origins_uses_explicit_deployment_allow_list() -> None:
    assert configured_origins("https://procurement.vercel.app, https://preview.vercel.app/") == [
        "https://procurement.vercel.app", "https://preview.vercel.app"
    ]
    assert configured_origins(None) == ["http://localhost:3000"]

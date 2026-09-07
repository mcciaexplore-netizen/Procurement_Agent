"""Compatibility entry point; the containerized worker lives under services/api."""

from app.application.jobs import stale_offer_sweep
from app.application.catalog import build_catalog


if __name__ == "__main__":
    print(stale_offer_sweep(build_catalog()))

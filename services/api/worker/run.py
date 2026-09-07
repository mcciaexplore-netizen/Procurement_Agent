"""One-shot worker entry point for scheduled maintenance."""

import argparse
import json

from app.application.catalog import build_catalog
from app.application.jobs import stale_offer_sweep


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=["stale-offer-sweep"], default="stale-offer-sweep")
    arguments = parser.parse_args()
    catalog = build_catalog()
    if arguments.job == "stale-offer-sweep":
        print(json.dumps(stale_offer_sweep(catalog)))

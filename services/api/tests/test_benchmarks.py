import json
from pathlib import Path

from app.application.catalog import build_seeded_catalog


def test_controlled_search_benchmark() -> None:
    catalog = build_seeded_catalog()
    benchmark_path = Path(__file__).parents[1] / "benchmarks" / "search_queries.json"
    queries = json.loads(benchmark_path.read_text())

    for benchmark in queries:
        groups = catalog.search(benchmark["query"], quantity=benchmark["quantity"])
        observed_mpns = [group["product"]["mpn"] for group in groups[: benchmark["top_n"]]]
        assert benchmark["expected_mpn"] in observed_mpns, benchmark["name"]

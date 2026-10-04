"""
The runs your test needs. ← UNIT 4, MILESTONE 3

Each of your five criteria needs something run against it. A criterion about
the empty-search branch needs an impossible query. One about the fit card needs
the same item run more than once. Working that out is Milestone 3's first step,
and this file is where you write it down.

`run_eval.py` runs everything here five times and writes the run log — five
because your criteria are written out of five.

Three scenarios are filled in to show the shape. Add or change whatever your
own criteria need — these are a starting point, not a fixed set.
"""

SCENARIOS = [
    {
        # Five distinct matching phrasings test the search's wording sensitivity.
        "name": "matching query completes",
        "query": "vintage graphic tee under $30",
        "queries": [
            "vintage graphic tee under $30",
            "butterfly baby tee below $25",
            "graphic tee 2003 tour bootleg under $30",
            "oversized flannel shirt red black under $40",
            "chunky brown knit cardigan under $60",
        ],
        "wardrobe": "example",
        "criterion": 1,
    },
    {
        # A query nothing can match. Criterion 2 — the branch.
        "name": "impossible query stops early",
        "query": "qzxv blorptastic nebuloid quuxorium",
        "wardrobe": "example",
        "criterion": 2,
    },
    {
        # Repeated matching queries let the trace compare the selected and passed item IDs.
        "name": "selected item reaches outfit tool",
        "query": "corduroy wide leg pants rust",
        "wardrobe": "example",
        "criterion": 3,
    },
    {
        # The same query selects the same listing across all five fit-card tries.
        "name": "fit card facts and length",
        "query": "90s silk slip dress floral midi length",
        "wardrobe": "example",
        "criterion": 4,
        "fixed_outfit": "The 90s floral silk midi slip dress layered under a chunky cream cardigan, with black ankle boots and a brown braided belt.",
    },
    {
        # Every returned listing must respect the explicit price ceiling.
        "name": "search respects price ceiling",
        "query": "graphic tee under $30",
        "wardrobe": "example",
        "criterion": 5,
    },
]

WARDROBES = ("example", "empty")


def validate() -> list[str]:
    """Complain about anything malformed, before a long run rather than during."""
    problems = []
    for i, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("query", "").strip():
            problems.append(f"scenario {i} has no query")
        queries = scenario.get("queries")
        if queries is not None:
            if not isinstance(queries, list) or len(queries) != 5:
                problems.append(f"scenario {i} must have exactly five query variants")
            elif any(not isinstance(query, str) or not query.strip() for query in queries):
                problems.append(f"scenario {i} has an empty query variant")
        if scenario.get("wardrobe") not in WARDROBES:
            problems.append(
                f"scenario {i} has wardrobe {scenario.get('wardrobe')!r} — "
                f"it should be one of {WARDROBES}"
            )
    return problems

import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="osb-test-")
os.environ["OSB_DATA_DIR"] = _tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json  # noqa: E402

import pytest  # noqa: E402

# Made-up venue rules for the tests. A real venue keeps its own in data/venue-rules.json.
TEST_RULES = {
    "aliases": [{"name": "Acme Syrups", "variant": "Plain Sugar", "to_name": "Gomme Syrup", "to_variant": "Original"}],
    "catalogue_match": {"gin": ["Bombay Sapphire Gin", "Original", 700], "cola": ["Coca-Cola", "Original", 7000],
                        "water sparkling|small": ["Small Water", "Sparkling", 330]},
    "postmix_items": ["cola"], "postmix_parts": 6, "dash_ml": 25, "shot_ml": 25,
    "regular_size": {"house shot": 25}, "variation_size": {"reserve": 25},
    "bar_categories": ["SPIRITS", "SOFT DRINKS", "COCKTAILS"], "uncategorised_drinks": ["negroni"],
}


@pytest.fixture(autouse=True)
def venue_rules():
    path = os.path.join(_tmp, "venue-rules.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(TEST_RULES, fh)
    yield TEST_RULES
    os.remove(path)

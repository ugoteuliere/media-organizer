import json
from pathlib import Path

TAGS_JSON_FILE = Path(__file__).resolve().parent / "tags.json"


def _load_core_data():
    if TAGS_JSON_FILE.is_file():
        with open(TAGS_JSON_FILE, encoding="utf-8") as f:
            data = json.load(f)
            categories = data.get("categories", {})
            tags = []
            for cat_list in categories.values():
                tags.extend(cat_list)
            return (tags, data.get("tlds", []), data.get("resolution_patterns", []), data.get("quality_patterns", []))
    return [], [], [], []


TAGS, TLDS, RESOLUTION_PATTERNS, QUALITY_PATTERNS = _load_core_data()

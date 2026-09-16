import re
import json
import tempfile
import shutil
from pathlib import Path
from src import ui
from src.config import config

# Comprehensive Stopwords Blacklist (EN & FR) to protect legitimate title words
STOPWORDS_BLACKLIST = {
    # English common words & pronouns
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "about",
    "against",
    "between",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "from",
    "up",
    "down",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "can",
    "will",
    "just",
    "should",
    "now",
    "war",
    "air",
    "man",
    "men",
    "boy",
    "girl",
    "her",
    "his",
    "its",
    "it",
    "my",
    "our",
    "your",
    "their",
    "we",
    "you",
    "us",
    "them",
    "film",
    "movie",
    "show",
    "series",
    "episode",
    "season",
    "video",
    "part",
    "audio",
    "music",
    "soundtrack",
    "love",
    "life",
    "night",
    "day",
    "world",
    "house",
    "time",
    "city",
    "star",
    "home",
    # French common words & pronouns
    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "du",
    "de",
    "au",
    "aux",
    "en",
    "dans",
    "par",
    "pour",
    "sur",
    "avec",
    "sans",
    "sous",
    "et",
    "ou",
    "mais",
    "donc",
    "or",
    "ni",
    "car",
    "ce",
    "cet",
    "cette",
    "ces",
    "mon",
    "ton",
    "son",
    "ma",
    "ta",
    "sa",
    "mes",
    "tes",
    "ses",
    "notre",
    "votre",
    "leur",
    "nos",
    "vos",
    "leurs",
    "je",
    "tu",
    "il",
    "elle",
    "on",
    "nous",
    "vous",
    "ils",
    "elles",
    "qui",
    "que",
    "quoi",
    "dont",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "vie",
    "mort",
    "nuit",
    "jour",
    "monde",
    "homme",
    "femme",
    "fille",
    "garcon",
    "roi",
    "reine",
    "guerre",
    "amour",
}

MIN_TAG_LENGTH = 3


class TagManager:
    """Manages 3-tier release tags: core defaults, user personal tags, and Gemini-learned tags."""

    def __init__(self, core_path=None, config_dir=None):
        if core_path:
            self.core_path = Path(core_path).resolve()
        else:
            self.core_path = Path(__file__).resolve().parent.parent / "data" / "tags.json"

        self._config_dir = Path(config_dir).resolve() if config_dir else None
        self._master_regex = None
        self._cached_tags = None

    @property
    def config_dir(self) -> Path:
        if self._config_dir is not None:
            return self._config_dir
        if hasattr(config, "config_path") and config.config_path:
            return config.config_path.parent
        return Path.home() / ".config" / "media-organizer"

    @property
    def user_tags_path(self) -> Path:
        return self.config_dir / "custom_tags.json"

    @property
    def gemini_tags_path(self) -> Path:
        return self.config_dir / "gemini_tags.json"

    def invalidate_cache(self):
        """Invalidates the compiled master regex and cached tag list."""
        self._master_regex = None
        self._cached_tags = None

    def load_core_tags(self) -> list[str]:
        """Loads default release tags shipped with the repository."""
        if not self.core_path.is_file():
            return []
        try:
            with open(self.core_path, encoding="utf-8") as f:
                data = json.load(f)
                categories = data.get("categories", {})
                tags = []
                for cat_list in categories.values():
                    if isinstance(cat_list, list):
                        tags.extend(str(item) for item in cat_list if str(item).strip())
                return tags
        except Exception as e:
            ui.print_log(f"⚠️ Warning: Failed to read core tags from {self.core_path}: {e}")
            return []

    def _extract_tags_from_json(self, file_path: Path) -> list[str]:
        """Helper to safely extract tags from a JSON list, dict, or nested structure."""
        if not file_path.is_file():
            return []
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                tags = []
                for item in data:
                    if isinstance(item, str):
                        tags.append(item.strip())
                    elif isinstance(item, dict) and "tag" in item:
                        tags.append(str(item["tag"]).strip())
                return [t for t in tags if t]
            elif isinstance(data, dict):
                if "tags" in data and isinstance(data["tags"], list):
                    return [str(t).strip() for t in data["tags"] if str(t).strip()]
                tags = []
                for val in data.values():
                    if isinstance(val, list):
                        tags.extend(str(item).strip() for item in val if str(item).strip())
                return tags
            return []
        except Exception as e:
            ui.print_log(f"⚠️ Warning: Failed to read tags from {file_path}: {e}")
            return []

    def load_user_tags(self) -> list[str]:
        """Loads user-defined personal keywords from <config_dir>/custom_tags.json."""
        return self._extract_tags_from_json(self.user_tags_path)

    def load_gemini_tags(self) -> list[str]:
        """Loads AI-learned keywords from <config_dir>/gemini_tags.json."""
        return self._extract_tags_from_json(self.gemini_tags_path)

    def get_all_tags(self) -> list[str]:
        """Merges all 3 tiers into a unified, deduplicated list."""
        if self._cached_tags is not None:
            return self._cached_tags

        seen = set()
        merged = []

        for tag in self.load_core_tags() + self.load_user_tags() + self.load_gemini_tags():
            clean = tag.strip()
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                merged.append(clean)

        self._cached_tags = merged
        return merged

    def get_master_regex(self) -> re.Pattern:
        """Compiles a single-pass master regex sorted by length descending."""
        if self._master_regex is not None:
            return self._master_regex

        # Core tags are repository-maintained regex patterns
        core_tags = self.load_core_tags()
        # User and Gemini tags are untrusted inputs that must be escaped to prevent ReDoS or syntax errors
        user_tags = [re.escape(t) for t in self.load_user_tags() if t.strip()]
        gemini_tags = [re.escape(t) for t in self.load_gemini_tags() if t.strip()]

        seen = set()
        tags = []
        for tag in core_tags + user_tags + gemini_tags:
            clean = tag.strip()
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                tags.append(clean)

        if not tags:
            self._master_regex = re.compile(r"(?!)")  # Matches nothing
            return self._master_regex

        # Sort tags by length in descending order so longest patterns match first
        sorted_tags = sorted(tags, key=len, reverse=True)

        # Build master regex using alphanumeric boundary assertions
        pattern_str = r"(?i)(?<![a-zA-Z0-9])(?:" + "|".join(sorted_tags) + r")(?![a-zA-Z0-9])"
        self._master_regex = re.compile(pattern_str)
        return self._master_regex

    def clean_text(self, text: str) -> str:
        """Strips all known release tags from the text in a single regex pass."""
        if not text:
            return text
        return self.get_master_regex().sub("", text)

    def validate_tag(self, tag: str) -> tuple[bool, str]:
        """Validates a candidate tag against length, format, and stopword rules."""
        if not tag or not isinstance(tag, str):
            return False, "Tag must be a non-empty string."

        clean = tag.strip()
        lower = clean.lower()

        if len(clean) < MIN_TAG_LENGTH:
            return False, f"Tag '{clean}' is too short (minimum {MIN_TAG_LENGTH} characters)."

        if lower in STOPWORDS_BLACKLIST:
            return False, f"Tag '{clean}' is a protected dictionary word / stopword."

        if clean.isdigit():
            return False, f"Tag '{clean}' is purely numeric."

        # Verify allowed characters (alphanumeric, dot, underscore, hyphen, plus)
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._+-]*$", clean):
            return False, f"Tag '{clean}' contains invalid characters."

        return True, clean

    def _atomic_append_json(self, file_path: Path, new_tags: list[str]) -> list[str]:
        """Atomically appends new tags to a target JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._extract_tags_from_json(file_path)
        existing_lower = {t.lower() for t in existing}

        added = []
        for tag in new_tags:
            valid, res = self.validate_tag(tag)
            if valid and res.lower() not in existing_lower:
                existing.append(res)
                existing_lower.add(res.lower())
                added.append(res)

        if not added:
            return []

        payload = {"tags": existing}
        with tempfile.NamedTemporaryFile("w", dir=file_path.parent, delete=False, encoding="utf-8") as tf:
            json.dump(payload, tf, indent=2)
            temp_name = tf.name

        shutil.move(temp_name, str(file_path))
        self.invalidate_cache()
        return added

    def add_gemini_tags(self, missing_tags: list[str]) -> list[str]:
        """Safely validates and appends AI-discovered tags to <config_dir>/gemini_tags.json."""
        if not missing_tags:
            return []

        core_and_user = {t.lower() for t in self.load_core_tags() + self.load_user_tags()}
        filtered = []

        for candidate in missing_tags:
            valid, res = self.validate_tag(candidate)
            if not valid:
                ui.print_log(f" ⚠️ Ignored unsafe tag from Gemini: {res}")
                continue
            if res.lower() in core_and_user:
                continue
            filtered.append(res)

        added = self._atomic_append_json(self.gemini_tags_path, filtered)
        for t in added:
            ui.print_log(f" ✅ Learned new tag from Gemini: {t}")
        return added

    def add_user_tags(self, tags: list[str]) -> list[str]:
        """Appends user-specified keywords to <config_dir>/custom_tags.json."""
        return self._atomic_append_json(self.user_tags_path, tags)


# Global singleton instance
tag_manager = TagManager()

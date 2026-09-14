import sys
import os
import re
import difflib
import uuid
from typing import Tuple, Optional
import PTN
import pandas as pd
from pathlib import Path
from src import ui, api, mail, files
from data.data import TAGS, TLDS, QUALITY_PATTERNS, RESOLUTION_PATTERNS
from src.tags import tag_manager

from src.config import config
MOVIES_FOLDER = getattr(config, 'MOVIES_FOLDER', None)
TV_SHOWS_FOLDER = getattr(config, 'TV_SHOWS_FOLDER', None)
NOT_SORTED_MEDIA_FILES_FOLDER = getattr(config, 'NOT_SORTED_MEDIA_FILES_FOLDER', None)
RESOLUTION = getattr(config, 'RESOLUTION', False)
QUALITY = getattr(config, 'QUALITY', False)

DEFAULT_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "data.py"
DATA_FILE = DEFAULT_DATA_FILE

def check_folder_permissions(folder_path) -> Tuple[bool, bool, str]:
    """
    Checks whether a folder has both read and write permissions.
    Returns (can_read, can_write, error_detail).
    """
    p = Path(folder_path)
    # Check Read:
    try:
        with os.scandir(p):
            pass
        can_read = True
    except (PermissionError, OSError) as e:
        return False, False, f"Read permission denied: {e}"

    # Check Write:
    probe_path = p / f".rename_perm_probe_{uuid.uuid4().hex}"
    try:
        probe_path.touch()
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass
        can_write = True
    except (PermissionError, OSError) as e:
        return True, False, f"Write permission denied: {e}"

    return True, True, ""

def verify_folders(only_rename=False, custom_path=None, daemon=False, simulate=False):
    def _get_folder(attr_name):
        val = globals().get(attr_name)
        if val is None or str(val).strip() == "":
            val = getattr(config, attr_name, None)
        return val

    if daemon:
        required_folders = [
            ("paths.movies_folder", _get_folder("MOVIES_FOLDER"), "MOVIES_FOLDER", "Movies folder"),
            ("paths.tv_shows_folder", _get_folder("TV_SHOWS_FOLDER"), "TV_SHOWS_FOLDER", "TV Shows folder"),
            ("paths.not_sorted_media_files_folder", _get_folder("NOT_SORTED_MEDIA_FILES_FOLDER"), "NOT_SORTED_MEDIA_FILES_FOLDER", "Unsorted downloads folder"),
        ]
    elif custom_path and only_rename:
        required_folders = [
            ("cli.path", custom_path, "PATH", "Custom source folder"),
        ]
    elif custom_path:
        required_folders = [
            ("cli.path", custom_path, "PATH", "Custom source folder"),
            ("paths.movies_folder", _get_folder("MOVIES_FOLDER"), "MOVIES_FOLDER", "Movies folder"),
            ("paths.tv_shows_folder", _get_folder("TV_SHOWS_FOLDER"), "TV_SHOWS_FOLDER", "TV Shows folder"),
        ]
    elif only_rename:
        required_folders = [
            ("paths.not_sorted_media_files_folder", _get_folder("NOT_SORTED_MEDIA_FILES_FOLDER"), "NOT_SORTED_MEDIA_FILES_FOLDER", "Unsorted downloads folder"),
        ]
    else:
        required_folders = [
            ("paths.movies_folder", _get_folder("MOVIES_FOLDER"), "MOVIES_FOLDER", "Movies folder"),
            ("paths.tv_shows_folder", _get_folder("TV_SHOWS_FOLDER"), "TV_SHOWS_FOLDER", "TV Shows folder"),
            ("paths.not_sorted_media_files_folder", _get_folder("NOT_SORTED_MEDIA_FILES_FOLDER"), "NOT_SORTED_MEDIA_FILES_FOLDER", "Unsorted downloads folder"),
        ]
    
    unconfigured = []
    for key_path, val, attr, label in required_folders:
        if val is None or str(val).strip() == "":
            unconfigured.append(f"  • {label} ({key_path} / {attr})")

    if unconfigured:
        if daemon:
            msg = (
                "❌ Missing configuration:\n"
                "Daemon mode requires all library and download folders to be configured:\n"
                + "\n".join(unconfigured) + "\n\n"
                "💡 How to fix:\n"
                "  1. Run the interactive setup wizard:\n"
                "     python main.py configure\n"
                "  2. Or set individual values via CLI:\n"
                "     python main.py config --set paths.movies_folder \"path/to/movies\"\n"
                "     python main.py config --set paths.tv_shows_folder \"path/to/tv_shows\"\n"
                "     python main.py config --set paths.not_sorted_media_files_folder \"path/to/downloads\"\n\n"
                "Stopping program."
            )
        elif custom_path:
            msg = (
                "❌ Missing configuration:\n"
                "Moving renamed files requires the destination library folders to be configured:\n"
                + "\n".join(unconfigured) + "\n\n"
                "💡 How to fix:\n"
                "  1. Run the interactive setup wizard:\n"
                "     python main.py configure\n"
                "  2. Or set library paths via CLI:\n"
                "     python main.py config --set paths.movies_folder \"path/to/movies\"\n"
                "     python main.py config --set paths.tv_shows_folder \"path/to/tv_shows\"\n"
                "  3. Or rename files in-place without moving them (standalone):\n"
                f"     python main.py -r --path=\"{custom_path}\"\n\n"
                "Stopping program."
            )
        elif only_rename:
            msg = (
                "❌ Missing configuration:\n"
                "The following required folder path is not configured:\n"
                + "\n".join(unconfigured) + "\n\n"
                "💡 How to fix:\n"
                "  1. Run the interactive setup wizard:\n"
                "     python main.py configure\n"
                "  2. Or specify a folder directly with --path:\n"
                "     python main.py -r --path \"path/to/folder\"\n"
                "  3. Or set the downloads folder via CLI:\n"
                "     python main.py config --set paths.not_sorted_media_files_folder \"path/to/downloads\"\n\n"
                "Stopping program."
            )
        else:
            msg = (
                "❌ Missing configuration:\n"
                "The following required folder paths are not configured:\n"
                + "\n".join(unconfigured) + "\n\n"
                "💡 How to fix:\n"
                "  1. Run the interactive setup wizard:\n"
                "     python main.py configure\n"
                "  2. Or set individual values via CLI:\n"
                "     python main.py config --set paths.movies_folder \"path/to/movies\"\n"
                "     python main.py config --set paths.tv_shows_folder \"path/to/tv_shows\"\n"
                "     python main.py config --set paths.not_sorted_media_files_folder \"path/to/downloads\"\n"
                "  3. Or use environment variables (e.g. RENAME_MOVIES_FOLDER)\n\n"
                "Stopping program."
            )
        ui.print_log(msg)
        sys.exit(1)

    missing_folders = []
    for key_path, folder_path, attr, label in required_folders:
        if not os.path.isdir(str(folder_path)):
            missing_folders.append(f"  • {folder_path} ({label})")

    if missing_folders:
        msg = (
            "❌ Missing required folder(s) on disk:\n"
            + "\n".join(missing_folders) + "\n\n"
            "💡 Please create the directory or update your configuration:\n"
            "   python main.py config --set <key> \"correct/path\"\n\n"
            "Stopping program."
        )
        ui.print_log(msg)
        sys.exit(1)

    permission_issues = []
    for key_path, folder_path, attr, label in required_folders:
        can_read, can_write, err_detail = check_folder_permissions(folder_path)
        if not can_read or (not simulate and not can_write):
            permission_issues.append(f"  • {folder_path} ({label}): {err_detail}")

    if permission_issues:
        msg = (
            "❌ Permission error:\n"
            "The program does not have the required read and write permissions for the following folder(s):\n"
            + "\n".join(permission_issues) + "\n\n"
            "💡 How to fix:\n"
            "  1. Grant read and write permissions on your system or NAS:\n"
            "     chmod -R u+rwX \"path/to/folder\"\n"
            "  2. In Docker, ensure PUID and PGID environment variables match the folder owner:\n"
            "     PUID=1000, PGID=1000\n"
            "  3. Check filesystem ACLs or share permissions (e.g. TrueNAS, Unraid, SMB/NFS).\n\n"
            "Stopping program."
        )
        ui.print_log(msg)
        sys.exit(1)

    return 0

def add_new_tags(missing_tags):
    if not missing_tags:
        return []

    # Safe 3-tier JSON learning with guardrails
    tag_manager.add_gemini_tags(missing_tags)

    # Backward compatibility with legacy tests pointing DATA_FILE to custom mock files
    if DATA_FILE != DEFAULT_DATA_FILE:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError as e:
            raise RuntimeError(ui.print_error(f" ❌ Error: The file {DATA_FILE} does not exist", e))

        tags_to_add = []
        for tag in missing_tags:
            clean_tag = tag.strip().lower()
            if not clean_tag:
                continue

            escaped_tag = re.escape(clean_tag)
            if f"r'{escaped_tag}'" not in content and f"r'{clean_tag}'" not in content:
                tags_to_add.append(escaped_tag)

        if not tags_to_add:
            return []

        new_tags_formatted = ", ".join([f"r'{tag}'" for tag in tags_to_add])

        pattern = re.compile(r"(TAGS\s*=\s*\[)([^\]]*)\]")
        match = pattern.search(content)

        if match:
            group1 = match.group(1)
            if not group1.strip().endswith(','):
                group1 += ','

            injection = f"\n    # === Ajout Auto Gemini ===\n    {new_tags_formatted}"
            new_content = content[:match.end(1)] + injection + content[match.start(2):]

            with open(DATA_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)

            ui.print_log(f" ✅ New tag(s) added to {DATA_FILE.name} : {tags_to_add}")
        else:
            ui.print_log(f" ❌ Error : Impossible to find TAGS list {DATA_FILE.name}")

SEASON_EPISODE_PATTERNS = [
    # 1. Saison/Season XX (Episode/Ep/E) XX (ex: Saison.01E02, Saison.1E2, Season.01.Episode.02, Saison 01 Ep 02)
    re.compile(r'\b(?:saison|season)[.\s_-]*(\d{1,2})[.\s_-]*(?:episode|ep|e)[.\s_-]*(\d{1,3})\b', re.IGNORECASE),
    # 2. SXX (Episode/Ep) XX (ex: S01.Episode.02, S01.Ep.02, S1 Episode 2)
    re.compile(r'\bs(\d{1,2})[.\s_-]*(?:episode|ep)[.\s_-]*(\d{1,3})\b', re.IGNORECASE),
    # 3. SXX séparé de EXX (ex: S01.E02, S01-E02, S1.E2)
    re.compile(r'\bs(\d{1,2})[.\s_-]+e(\d{1,3})\b', re.IGNORECASE),
]

def normalize_season_episode(filename: str) -> str:
    if not filename:
        return filename
    for pattern in SEASON_EPISODE_PATTERNS:
        def repl(match):
            s = int(match.group(1))
            e = int(match.group(2))
            return f"S{s:02d}E{e:02d}"

        new_filename, count = pattern.subn(repl, filename)
        if count > 0:
            return new_filename
    return filename

def parse_season_episode(season, episode, filename):
    try:
        s = int(season)
        e = int(episode)
    except (ValueError, TypeError):
        norm_filename = normalize_season_episode(filename)
        season_regex = r'(?:saison|season|s)[.\s-]*(\d+)'
        episode_regex = r'(?:episode|ep|e)[.\s-]*(\d+)'

        s_match = re.search(season_regex, norm_filename, re.IGNORECASE)
        e_match = re.search(episode_regex, norm_filename, re.IGNORECASE)

        if s_match and e_match:
            s = int(s_match.group(1))
            e = int(e_match.group(1))
        else:
            raise ValueError(f"Could not extract season/episode from filename: {filename}")

    return s, e

def parse_resolution_quality(resolution_ptn, quality_ptn, resolution_clean, quality_clean, file):
    if not RESOLUTION and not QUALITY:
        return None, None

    # resolution
    if resolution_ptn and str(resolution_ptn).strip():
        final_resolution = resolution_ptn
    elif resolution_clean and str(resolution_clean).strip():
        final_resolution = resolution_clean
    else:
        final_resolution = None

    # quality
    if quality_ptn and str(quality_ptn).strip():
        final_quality = quality_ptn
    elif quality_clean and str(quality_clean).strip():
        final_quality = quality_clean
    else:
        final_quality = None

    # scan file
    if final_resolution is None or final_quality is None:
        res_file, qual_file = files.get_file_quality_resolution(file)
        
        # Update resolution if it was not found previously
        if final_resolution is None and res_file and str(res_file).strip():
            final_resolution = res_file
            
        # Update quality if it was not found previously
        if final_quality is None and qual_file and str(qual_file).strip():
            final_quality = qual_file

    return translate_resolution_to_name(final_resolution), final_quality

def translate_resolution_to_name(resolution_str):
    if not resolution_str:
        return None

    mapping = {
        "2160p": "4K",
        "1440p": "2K",
        "1080p": "FullHD",
        "720p": "HD",
        "480p": "SD",
        "576p": "SD"
    }

    clean_res = str(resolution_str).strip().lower()
    return mapping.get(clean_res, resolution_str)

def format_season_and_episode(season, episode):
    try:
        season = int(season)
        episode = int(episode)
    except (ValueError, TypeError):
        raise ValueError("Failed parsing season or episode")

    if season < 10:
        season = "0" + str(season)
    else: 
        season = str(season)

    if episode < 10:
        episode = "0" + str(episode)
    else:
        episode = str(episode)

    return season, episode

def sort_media_dataframe(df):
    if df.empty:
        return df
    return df.sort_values(
        by=['Corrected', 'Season', 'Episode'], 
        ascending=[True, True, True], 
        ignore_index=True
    )

def compute_tmdb_match_probability(parsed_name: str | None, parsed_year: str | None, tmdb_title: str | None, tmdb_year: str | None) -> float:
    """
    Computes a match probability P in [0.0, 1.0] between locally parsed media metadata
    and TMDB API search results. Combines string sequence similarity, token-set overlap,
    and year proximity.
    """
    if not parsed_name or not tmdb_title or tmdb_title == "unknown":
        return 0.0

    def _normalize(text: str) -> str:
        text = str(text).lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return " ".join(text.split())

    norm_parsed = _normalize(parsed_name)
    norm_tmdb = _normalize(tmdb_title)

    if not norm_parsed or not norm_tmdb:
        return 0.0

    # 1. Sequence ratio
    seq_ratio = difflib.SequenceMatcher(None, norm_parsed, norm_tmdb).ratio()

    # 2. Token overlap & containment
    tokens_p = set(norm_parsed.split())
    tokens_t = set(norm_tmdb.split())
    intersection = tokens_p & tokens_t
    if intersection:
        jaccard = len(intersection) / len(tokens_p | tokens_t)
        containment = len(intersection) / min(len(tokens_p), len(tokens_t))
        token_score = max(jaccard, 0.85 * containment)
    else:
        token_score = 0.0

    title_similarity = max(seq_ratio, token_score, 0.5 * seq_ratio + 0.5 * token_score)

    # 3. Year factor
    year_factor = 1.0
    p_year_clean = str(parsed_year).strip() if parsed_year and str(parsed_year).strip() not in ("None", "unknown", "") else None
    t_year_clean = str(tmdb_year).strip() if tmdb_year and str(tmdb_year).strip() not in ("None", "unknown", "") else None

    if p_year_clean and t_year_clean:
        try:
            py_int = int(p_year_clean[:4])
            ty_int = int(t_year_clean[:4])
            diff = abs(py_int - ty_int)
            if diff == 0:
                year_factor = 1.0
            elif diff == 1:
                year_factor = 0.95
            elif diff <= 2:
                year_factor = 0.85
            else:
                year_factor = max(0.4, 1.0 - (diff * 0.1))
        except (ValueError, TypeError):
            year_factor = 0.90
    elif p_year_clean and not t_year_clean:
        year_factor = 0.85
    elif not p_year_clean and t_year_clean:
        year_factor = 0.90
    else:
        year_factor = 0.90

    final_score = title_similarity * year_factor
    return round(min(1.0, max(0.0, final_score)), 2)


def correct_movie_filename(file, ai_result=None):
    
    new_filename = None

    try:
        name = file['Parse'][0]
        year = file['Parse'][1]

        resolution, quality = parse_resolution_quality(
            file['Parse'][2], file['Parse'][3],
            file['Clean'][2], file['Clean'][3],
            file['Path']
        )

        min_conf = getattr(config, 'TMDB_MIN_CONFIDENCE', 0.75)

        if ai_result is not None:
            success, title, year, original_language = ai_result[0], ai_result[1], ai_result[2], ai_result[3]
        else:
            success, title, tmdb_year, original_language = api.api_call(name, year, "en-US", "movie")
            best_tmdb = (success, title, tmdb_year, original_language)
            if success:
                prob = compute_tmdb_match_probability(name, year, title, tmdb_year)
                if prob < min_conf and ui.AI_FALLBACK_ENABLED:
                    success = False

            if not success: 
                name = file['Clean'][0]
                year = file['Clean'][1]
                
                clean_s, clean_t, clean_y, clean_l = api.api_call(name, year, "en-US", "movie")
                if clean_s:
                    prob_c = compute_tmdb_match_probability(name, year, clean_t, clean_y)
                    if prob_c >= min_conf or not ui.AI_FALLBACK_ENABLED:
                        success, title, tmdb_year, original_language = True, clean_t, clean_y, clean_l
                        best_tmdb = (True, clean_t, clean_y, clean_l)
                    else:
                        success = False
                
                if not success and ui.AI_FALLBACK_ENABLED:
                    ai_res = api.gemini_api_call(file)
                    if ai_res and ai_res[0]:
                        success, title, tmdb_year, original_language = True, ai_res[1], ai_res[2], ai_res[3]
                    elif best_tmdb[0]:
                        success, title, tmdb_year, original_language = best_tmdb
            
            if success:
                year = tmdb_year
        
        if success and original_language in ["fr", "fr-FR"]:
            success_fr, title_fr, year_fr, _ = api.api_call(name, year, "fr-FR", "movie")
            if success_fr:
                title = title_fr 
                year = year_fr
        
        new_filename = generate_new_movie_filename(success, title, year, resolution, quality)
            
    except Exception as e:
        failed_file = file.get('File', 'Unknown File')

        error_message = (
                f"Impossible to rename the following file: {failed_file}\n\n"
                f"⤷ Error logs: {e}\n"
            )
        
        mail.send_error_email(error_message=error_message, affected_file=failed_file, exception=e)

        if ui.VERBOSE_ENABLED:  
            ui.print_log(error_message)
        
        new_filename = None

    return new_filename


def correct_tv_show_filename(file, ai_result=None):

    new_filename = None
    season = None
    episode = None

    try:
        name = file['Parse'][0]

        season, episode = parse_season_episode(file['Parse'][2], file['Parse'][3], file['File'])
        season, episode = format_season_and_episode(season, episode)
        resolution, quality = parse_resolution_quality(
            file['Parse'][4], file['Parse'][5],
            file['Clean'][2], file['Clean'][3],
            file['Path']
        )
        
        min_conf = getattr(config, 'TMDB_MIN_CONFIDENCE', 0.75)

        if ai_result is not None:
            success, title, _, original_language = ai_result[0], ai_result[1], ai_result[2], ai_result[3]
        else:
            success, title, _, original_language = api.api_call(name, None, "en-US", "tv")
            best_tmdb = (success, title, original_language)
            if success:
                prob = compute_tmdb_match_probability(name, None, title, None)
                if prob < min_conf and ui.AI_FALLBACK_ENABLED:
                    success = False

            if not success:
                name = file['Clean'][0]
                clean_s, clean_t, _, clean_l = api.api_call(name, None, "en-US", "tv")
                if clean_s:
                    prob_c = compute_tmdb_match_probability(name, None, clean_t, None)
                    if prob_c >= min_conf or not ui.AI_FALLBACK_ENABLED:
                        success, title, original_language = True, clean_t, clean_l
                        best_tmdb = (True, clean_t, clean_l)
                    else:
                        success = False

                if not success and ui.AI_FALLBACK_ENABLED:
                    ai_res = api.gemini_api_call(file)
                    if ai_res and ai_res[0]:
                        success, title, original_language = True, ai_res[1], ai_res[3]
                    elif best_tmdb[0]:
                        success, title, original_language = best_tmdb
            
        if success and original_language in ["fr", "fr-FR"]:
            success_fr, title_fr, _, _ = api.api_call(name, None, "fr-FR", "tv")
            if success_fr:
                title = title_fr

        new_filename = generate_new_tvshow_filename(success, title, season, episode, resolution, quality)
    
    except Exception as e:
        failed_file = file.get('File', 'Unknown File')

        error_message = (
                f"Impossible to rename the following file: {failed_file}\n\n"
                f"⤷ Error logs: {e}\n"
            )
        
        mail.send_error_email(error_message=error_message, affected_file=failed_file, exception=e)

        if ui.VERBOSE_ENABLED:  
            ui.print_log(error_message)
        
        new_filename = None
        season = None
        episode = None

    return new_filename, season, episode

def sanitize_filename(name: str) -> str:
    """Sanitizes a title or filename component against directory traversal and forbidden characters."""
    if not name or not isinstance(name, str):
        return ""

    # Replace colons with standard title separator " -"
    sanitized = name.replace(":", " -")

    # Remove directory traversal segments (e.g. "../" or "..\" or standalone "..")
    sanitized = re.sub(r'(?:\.\.[\\/]+)+', '', sanitized)
    sanitized = re.sub(r'\.{2,}', '', sanitized)

    # Replace illegal filesystem characters (\ / * ? " < > | and null bytes) with hyphen
    sanitized = re.sub(r'[\x00\\/*?"<>|]', '-', sanitized)

    # Collapse multiple consecutive hyphens or spaces
    sanitized = re.sub(r'-{2,}', '-', sanitized)
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Strip leading/trailing dots, hyphens, and whitespace
    sanitized = sanitized.strip('. -')

    return sanitized

def generate_new_movie_filename(success, title, year, resolution, quality):
    is_title_valid = title and str(title).strip()

    if not success or not is_title_valid :
        raise LookupError("API calls failed or essential metadata (Title) is missing/empty.")

    safe_title = sanitize_filename(title)
    if not safe_title:
        raise LookupError("Title contains only invalid characters.")

    new_name = safe_title
    if year and str(year).strip():
        safe_year = re.sub(r'[^0-9]', '', str(year).strip())
        if safe_year:
            new_name += f" ({safe_year})"

    # quality and resolution
    metadata_parts = []
    if QUALITY and quality and str(quality).strip():
        metadata_parts.append(str(quality))
    if RESOLUTION and resolution and str(resolution).strip():
        metadata_parts.append(str(resolution))
    if metadata_parts:
        new_name += f" [{' '.join(metadata_parts)}]"

    return new_name

def generate_new_tvshow_filename(success, title, season, episode, resolution=None, quality=None):
    is_title_valid = title and str(title).strip()
    is_season_valid = season is not None and str(season).strip() != ""
    is_episode_valid = episode is not None and str(episode).strip() != ""

    if not success or not is_title_valid or not is_season_valid or not is_episode_valid:
        raise LookupError("API calls failed or essential metadata (Title, Season, or Episode) is missing/empty.")

    safe_title = sanitize_filename(title)
    if not safe_title:
        raise LookupError("Title contains only invalid characters.")

    new_name = safe_title

    # season and episode
    s_padded = str(season).zfill(2)
    e_padded = str(episode).zfill(2)
    new_name += f" - S{s_padded}E{e_padded}"

    # quality and resolution
    metadata_parts = []
    if QUALITY and quality and str(quality).strip():
        metadata_parts.append(str(quality))
    if RESOLUTION and resolution and str(resolution).strip():
        metadata_parts.append(str(resolution))
    if metadata_parts:
        new_name += f" [{' '.join(metadata_parts)}]"

    return new_name

def remove_url(filename):
    # setup
    tlds_pattern = '|'.join(TLDS)
    url_pattern = rf"""
        (?:
            # CASE 1: Starts with 'www.' (Safe to greedily capture multiple subdomains)
            (?:\b|(?<=_))www\.(?:[a-zA-Z0-9-]+\.)+(?:{tlds_pattern})(?:\b|(?=_))
            
            | # OR
            
            # CASE 2: No 'www.' (Strictly ONE word before the TLD chain)
            # This captures "site.com" or "amazon.co.uk" but stops before "My.Movie."
            (?:\b|(?<=_))[a-zA-Z0-9-]+\.(?:(?:{tlds_pattern})\.)*(?:{tlds_pattern})(?:\b|(?=_))
        )
    """
    # clean
    clean_filename = re.sub(url_pattern, '', filename, flags=re.IGNORECASE | re.VERBOSE)
    clean_filename = re.sub(r'\[\s*\]|\(\s*\)', '', clean_filename)
    clean_filename = re.sub(r'\.{2,}', '.', clean_filename)
    clean_filename = clean_filename.strip('.-_ ')

    return clean_filename

def parse_filename(filename):
    filename = normalize_season_episode(filename)
    filename_without_url = remove_url(filename)
    filename_without_url = re.sub(r'\d{5,}', '', filename_without_url)
    filename_parsed = PTN.parse(filename_without_url)
    media = "tv" if (filename_parsed.get('season') or filename_parsed.get('episode')) else "movie"
    title = str(filename_parsed.get('title')) if filename_parsed.get('title') else ""
    year = str(filename_parsed.get('year')) if filename_parsed.get('year') else ""
    resolution = str(filename_parsed.get('resolution')) if filename_parsed.get('resolution') else ""
    quality = str(filename_parsed.get('quality')) if filename_parsed.get('quality') else ""
    if media == "movie" :
        parse = [title, year, resolution, quality]
    else : 
        season = str(filename_parsed.get('season')) if filename_parsed.get('season') else ""
        episode = str(filename_parsed.get('episode')) if filename_parsed.get('episode') else ""
        parse = [title, year, season, episode, resolution, quality]

    return parse, media

def clean_filename(filename):
    filename = normalize_season_episode(filename)
    raw_name = filename.rsplit('.', 1)[0]
    raw_name = raw_name.replace('_', '.')

    # remove urls
    filename_without_urls = remove_url(raw_name)
    
    # search for a year patern 
    year_match = re.search(r'\(?((?:19|20)\d{2})\)?', raw_name)
    year = year_match.group(1) if year_match else ""

    resolution = ""
    for pattern in RESOLUTION_PATTERNS:
        res_match = re.search(pattern, raw_name, flags=re.IGNORECASE)
        if res_match:
            resolution = res_match.group(0)
            break

    quality = ""
    for pattern in QUALITY_PATTERNS:
        qual_match = re.search(pattern, raw_name, flags=re.IGNORECASE)
        if qual_match:
            quality = qual_match.group(0)
            break

    # regex filters
    clean_title = re.sub(r'S\d+E\d+', '', filename_without_urls, flags=re.IGNORECASE)
    clean_title = re.sub(r'\d{5,}', '', clean_title)
    clean_title = re.sub(r'\(?(?:19|20)\d{2}\)?', '', clean_title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    
    # remove torrent file informations
    clean_title = tag_manager.clean_text(clean_title)
        
    # clean spaces
    clean_title = clean_title.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    clean_title = ' '.join(clean_title.split()).strip()
    
    return clean_title, year, resolution, quality

import pandas as pd

def handle_conflicts_and_duplicates(df, failed_files):
    if df.empty:
        return df

    # Identify all rows where the 'Corrected' name is a duplicate
    check_for_duplicates = df[df.duplicated(subset=['Corrected'], keep=False)]
    
    if not check_for_duplicates.empty:
        conflicts = check_for_duplicates['Corrected'].unique()
        for i in conflicts:
            # Find all original filenames associated with this specific conflict
            fichiers_originaux = check_for_duplicates[check_for_duplicates['Corrected'] == i]['Original'].tolist()
            
            for original_file in fichiers_originaux:
                failed_files.append({
                    'Original': original_file,
                    'Reason': f"Conflict: Multiple files resolve to '{i}'"
                })
        
        # Remove ALL conflicting rows from the dataframe
        df = df.drop_duplicates(subset=['Corrected'], keep=False)
    
    return df

def get_corrected_media_filenames(messy_data_table, clean_data_table):
    ui.print_log(f"\nAnalysing {len(messy_data_table)} files. Please wait...\n")
    
    new_clean_data_rows = []
    failed_files = []
    ai_results = {}

    if ui.AI_FALLBACK_ENABLED:
        ai_pending_items = []
        min_conf = getattr(config, "TMDB_MIN_CONFIDENCE", 0.75)

        for _, file in messy_data_table.iterrows():
            m_type = file.get("Media")
            if m_type not in ("movie", "tv"):
                continue

            needs_fallback = False
            if m_type == "movie":
                p_name, p_year = file['Parse'][0], file['Parse'][1]
                s, t, y, _ = api.api_call(p_name, p_year, "en-US", "movie")
                prob = compute_tmdb_match_probability(p_name, p_year, t, y) if s else 0.0
                if not (s and prob >= min_conf):
                    c_name, c_year = file['Clean'][0], file['Clean'][1]
                    s_c, t_c, y_c, _ = api.api_call(c_name, c_year, "en-US", "movie")
                    prob_c = compute_tmdb_match_probability(c_name, c_year, t_c, y_c) if s_c else 0.0
                    if not (s_c and prob_c >= min_conf):
                        needs_fallback = True
            elif m_type == "tv":
                p_name = file['Parse'][0]
                s, t, _, _ = api.api_call(p_name, None, "en-US", "tv")
                prob = compute_tmdb_match_probability(p_name, None, t, None) if s else 0.0
                if not (s and prob >= min_conf):
                    c_name = file['Clean'][0]
                    s_c, t_c, _, _ = api.api_call(c_name, None, "en-US", "tv")
                    prob_c = compute_tmdb_match_probability(c_name, None, t_c, None) if s_c else 0.0
                    if not (s_c and prob_c >= min_conf):
                        needs_fallback = True

            if needs_fallback:
                ai_pending_items.append(file)

        if ai_pending_items:
            ui.print_log(f"🤖 Queuing {len(ai_pending_items)} files for AI batch fallback...\n")
            BATCH_SIZE = 25
            for i in range(0, len(ai_pending_items), BATCH_SIZE):
                chunk = ai_pending_items[i : i + BATCH_SIZE]
                chunk_dicts = [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in chunk]
                batch_res = api.execute_ai_batch_with_failover(chunk_dicts)
                for file_obj, res in zip(chunk, batch_res):
                    ai_results[file_obj['File']] = res

    for _, file in messy_data_table.iterrows():
        f_name = file['File']
        ai_res = ai_results.get(f_name)

        if file['Media'] == "movie": 
            corrected_name = correct_movie_filename(file, ai_result=ai_res) 
            season, episode = None, None
        elif file['Media'] == "tv": 
            corrected_name, season, episode = correct_tv_show_filename(file, ai_result=ai_res) 
        else:
            ui.print_log(f"Ignored : {file['File']}\n")
            continue
            
        if corrected_name is None:
            failed_files.append({
                'Original': file['File'], 
                'Reason': 'API or parsing failed'
            })
        else:
            new_clean_data_rows.append({
                'Original': file['File'],
                'Corrected': corrected_name,
                'Path': file['Path'],
                'Media': file['Media'],
                'Season': season,
                'Episode': episode   
            })
            
    new_df = pd.DataFrame(new_clean_data_rows)
    df = pd.concat([clean_data_table, new_df], ignore_index=True) if not new_df.empty else clean_data_table

    df = sort_media_dataframe(df)
    df = handle_conflicts_and_duplicates(df, failed_files)

    ui.display_skipped_filenames(failed_files)
            
    return df

def has_files_to_rename(data_table):
    data_empty = data_table.empty
    if not data_empty:
        data_empty = True
        for _, row in data_table.iterrows(): 
            if row['Original'] != row['Corrected']:
                data_empty = False
    return not data_empty
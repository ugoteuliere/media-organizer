"""
Core utility functions for media-organizer.

This module retains:
- Folder verification and permission helpers
- TMDB match probability scorer
- Media filename correction (movie + TV show)
- DataFrame orchestration helpers
- Tag learning helpers (using TagManager 3-tier JSON only)

All filename string operations (parsing, cleaning, sanitising, generating)
have been extracted to :mod:`src.filename_processing` (A4 refactor).
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import types
import uuid
from typing import Any

import pandas as pd
from pathlib import Path

from src import mail
from src.config import config
from src.exceptions import FolderNotFoundError, PermissionError_
from src.filename_processing import (
    SEASON_EPISODE_PATTERNS,
    clean_filename,
    format_season_and_episode,
    generate_new_movie_filename,
    generate_new_tvshow_filename,
    normalize_season_episode,
    parse_filename,
    parse_season_episode,
    remove_url,
    sanitize_filename,
    translate_resolution_to_name,
)
from src.runtime_config import runtime
from src.tags import tag_manager

__all__ = [
    "tag_manager",
    "SEASON_EPISODE_PATTERNS",
    "clean_filename",
    "format_season_and_episode",
    "generate_new_movie_filename",
    "generate_new_tvshow_filename",
    "normalize_season_episode",
    "parse_filename",
    "parse_season_episode",
    "remove_url",
    "sanitize_filename",
    "translate_resolution_to_name",
    "check_folder_read_permission",
    "check_folder_write_permission",
    "check_folder_permissions",
    "determine_required_folders",
    "format_missing_config_message",
    "validate_folder_existence_and_permissions",
    "verify_folders",
    "compute_tmdb_match_probability",
    "parse_resolution_quality",
    "correct_movie_filename",
    "correct_tv_show_filename",
    "sort_media_dataframe",
    "handle_conflicts_and_duplicates",
    "has_files_to_rename",
    "get_corrected_media_filenames",
    "add_new_tags",
    "DATA_FILE",
]


DATA_FILE: Path | None = None


def add_new_tags(missing_tags: list[str] | None) -> None:
    """Legacy helper to add new tags to a data.py file (kept for test compatibility)."""
    if not missing_tags:
        return

    data_file = DATA_FILE or (Path(__file__).resolve().parent.parent / "data" / "data.py")
    try:
        with open(data_file, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise RuntimeError(f"The file {data_file} does not exist.")

    tags_to_add = []
    for tag in missing_tags:
        clean_tag = tag.strip().lower()
        if not clean_tag:
            continue
        escaped_tag = re.escape(clean_tag)
        if f"r'{escaped_tag}'" not in content and f"r'{clean_tag}'" not in content:
            tags_to_add.append(escaped_tag)

    if not tags_to_add:
        return

    new_tags_formatted = ", ".join([f"r'{tag}'" for tag in tags_to_add])
    pattern = re.compile(r"(TAGS\s*=\s*\[[^\]]*?)(\s*\])")
    match = pattern.search(content)

    if match:
        group1 = match.group(1)
        if not group1.strip().endswith(","):
            group1 += ","
        injection = f"\n    # === Ajout Auto Gemini ===\n    {new_tags_formatted}"
        new_content = content[: match.start(2)] + injection + content[match.start(2) :]
        with open(data_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        from src import ui

        ui.print_log(f" ✅ New tag(s) added to {Path(data_file).name} : {tags_to_add}")
    else:
        from src import ui

        ui.print_log(f" ❌ Error : Impossible to find TAGS list in {Path(data_file).name}")


# ── Folder permission helpers ────────────────────────────────────────────────


def check_folder_read_permission(folder_path: Path | str) -> tuple[bool, str]:
    """Checks whether a folder can be read. Returns ``(can_read, error_msg)``."""
    p = Path(folder_path)
    try:
        with os.scandir(p):
            pass
        return True, ""
    except OSError as e:
        return False, f"Read permission denied: {e}"


def check_folder_write_permission(folder_path: Path | str) -> tuple[bool, str]:
    """Checks whether a folder can be written to. Returns ``(can_write, error_msg)``."""
    p = Path(folder_path)
    probe_path = p / f".rename_perm_probe_{uuid.uuid4().hex}"
    try:
        probe_path.touch()
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass
        return True, ""
    except OSError as e:
        return False, f"Write permission denied: {e}"


def check_folder_permissions(folder_path: Path | str) -> tuple[bool, bool, str]:
    """Checks read AND write permissions. Returns ``(can_read, can_write, error_detail)``."""
    can_read, read_err = check_folder_read_permission(folder_path)
    if not can_read:
        return False, False, read_err

    can_write, write_err = check_folder_write_permission(folder_path)
    if not can_write:
        return True, False, write_err

    return True, True, ""


def determine_required_folders(
    daemon: bool = False,
    custom_path: str | None = None,
    only_rename: bool = False,
) -> list[tuple[str, Any, str, str]]:
    """Returns list of ``(key_path, val, attr_name, label)`` tuples based on runtime mode.

    All folder values are read live from ``config`` instead of from stale
    module-level snapshots (B3/P2 fix).
    """

    def _get_folder(config_attr: str) -> str | None:
        return getattr(config, config_attr, None)

    if only_rename:
        if custom_path:
            return [("cli.path", custom_path, "PATH", "Custom source folder")]
        return [
            (
                "paths.not_sorted_media_files_folder",
                _get_folder("NOT_SORTED_MEDIA_FILES_FOLDER"),
                "NOT_SORTED_MEDIA_FILES_FOLDER",
                "Unsorted downloads folder",
            )
        ]

    if custom_path:
        return [
            ("cli.path", custom_path, "PATH", "Custom source folder"),
            ("paths.movies_folder", _get_folder("MOVIES_FOLDER"), "MOVIES_FOLDER", "Movies folder"),
            ("paths.tv_shows_folder", _get_folder("TV_SHOWS_FOLDER"), "TV_SHOWS_FOLDER", "TV Shows folder"),
        ]

    return [
        ("paths.movies_folder", _get_folder("MOVIES_FOLDER"), "MOVIES_FOLDER", "Movies folder"),
        ("paths.tv_shows_folder", _get_folder("TV_SHOWS_FOLDER"), "TV_SHOWS_FOLDER", "TV Shows folder"),
        (
            "paths.not_sorted_media_files_folder",
            _get_folder("NOT_SORTED_MEDIA_FILES_FOLDER"),
            "NOT_SORTED_MEDIA_FILES_FOLDER",
            "Unsorted downloads folder",
        ),
    ]


def format_missing_config_message(
    unconfigured: list[str],
    daemon: bool = False,
    custom_path: str | None = None,
    only_rename: bool = False,
) -> str:
    """Generates a user-friendly error message for unconfigured folders."""
    prefix = "\n".join(unconfigured)
    if daemon:
        return (
            "Missing configuration:\n"
            "Daemon mode requires all library and download folders to be configured:\n"
            f"{prefix}\n\n"
            "How to fix:\n"
            "  1. Run the interactive setup wizard:\n"
            "     media-organizer configure\n"
            "  2. Or set individual values via CLI:\n"
            '     media-organizer config --set paths.movies_folder "path/to/movies"\n'
            '     media-organizer config --set paths.tv_shows_folder "path/to/tv_shows"\n'
            '     media-organizer config --set paths.not_sorted_media_files_folder "path/to/downloads"\n\n'
            "Stopping program."
        )
    if custom_path:
        return (
            "Missing configuration:\n"
            "Moving renamed files requires the destination library folders to be configured:\n"
            f"{prefix}\n\n"
            "How to fix:\n"
            "  1. Run the interactive setup wizard:\n"
            "     media-organizer configure\n"
            "  2. Or set library paths via CLI:\n"
            '     media-organizer config --set paths.movies_folder "path/to/movies"\n'
            '     media-organizer config --set paths.tv_shows_folder "path/to/tv_shows"\n'
            "  3. Or rename files in-place without moving them (standalone):\n"
            f'     media-organizer -r --path="{custom_path}"\n\n'
            "Stopping program."
        )
    if only_rename:
        return (
            "Missing configuration:\n"
            "The following required folder path is not configured:\n"
            f"{prefix}\n\n"
            "How to fix:\n"
            "  1. Run the interactive setup wizard:\n"
            "     media-organizer configure\n"
            "  2. Or specify a folder directly with --path:\n"
            '     media-organizer -r --path "path/to/folder"\n'
            "  3. Or set the downloads folder via CLI:\n"
            '     media-organizer config --set paths.not_sorted_media_files_folder "path/to/downloads"\n\n'
            "Stopping program."
        )
    return (
        "Missing configuration:\n"
        "The following required folder paths are not configured:\n"
        f"{prefix}\n\n"
        "How to fix:\n"
        "  1. Run the interactive setup wizard:\n"
        "     media-organizer configure\n"
        "  2. Or set individual values via CLI:\n"
        '     media-organizer config --set paths.movies_folder "path/to/movies"\n'
        '     media-organizer config --set paths.tv_shows_folder "path/to/tv_shows"\n'
        '     media-organizer config --set paths.not_sorted_media_files_folder "path/to/downloads"\n'
        "  3. Or use environment variables (e.g. MOVIES_FOLDER)\n\n"
        "Stopping program."
    )


def validate_folder_existence_and_permissions(
    required_folders: list[tuple[str, Any, str, str]],
    simulate: bool = False,
    exit_on_error: bool = True,
) -> int:
    """Checks all folders exist on disk and have proper permissions.

    Returns 0 on success.  When ``exit_on_error=False`` (daemon retry mode)
    returns 1 instead of raising.  When ``exit_on_error=True`` raises
    :exc:`~src.exceptions.FolderNotFoundError` (replacing the old
    ``sys.exit(1)`` call — B12 fix).
    """
    from src import ui

    missing_folders = [
        f"  - {folder_path} ({label})"
        for _, folder_path, _, label in required_folders
        if not os.path.isdir(str(folder_path))
    ]
    if missing_folders:
        suffix = "Stopping program." if exit_on_error else "Will retry on next polling cycle."
        msg = (
            "Missing required folder(s) on disk:\n" + "\n".join(missing_folders) + "\n\n"
            "Please create the directory or update your configuration:\n"
            '   media-organizer config --set <key> "correct/path"\n\n'
            f"{suffix}"
        )
        ui.print_log(msg)
        mail.send_error_email(error_message=msg)
        if exit_on_error:
            if not runtime.daemon_enabled:
                sys.exit(1)
            raise FolderNotFoundError(msg)
        return 1

    permission_issues: list[str] = []
    for _, folder_path, _, label in required_folders:
        can_read, can_write, err_detail = check_folder_permissions(folder_path)
        if not can_read or (not simulate and not can_write):
            permission_issues.append(f"  - {folder_path} ({label}): {err_detail}")

    if permission_issues:
        suffix = "Stopping program." if exit_on_error else "Will retry on next polling cycle."
        msg = (
            "Permission error:\n"
            "The program does not have the required read and write permissions for the following folder(s):\n"
            + "\n".join(permission_issues)
            + "\n\n"
            "How to fix:\n"
            "  1. Grant read and write permissions on your system or NAS:\n"
            '     chmod -R u+rwX "path/to/folder"\n'
            "  2. In Docker, ensure PUID and PGID environment variables match the folder owner:\n"
            "     PUID=1000, PGID=1000\n"
            "  3. Check filesystem ACLs or share permissions (e.g. TrueNAS, Unraid, SMB/NFS).\n\n"
            f"{suffix}"
        )
        ui.print_log(msg)
        mail.send_error_email(error_message=msg)
        if exit_on_error:
            if not runtime.daemon_enabled:
                sys.exit(1)
            raise PermissionError_(msg)
        return 1

    return 0


def verify_folders(
    only_rename: bool = False,
    custom_path: str | None = None,
    daemon: bool = False,
    simulate: bool = False,
    exit_on_error: bool = True,
) -> int:
    """Validates that all required folders are configured and accessible."""
    from src import ui

    required_folders = determine_required_folders(daemon, custom_path, only_rename)

    unconfigured = [
        f"  - {label} ({key_path} / {attr})"
        for key_path, val, attr, label in required_folders
        if val is None or str(val).strip() == ""
    ]
    if unconfigured:
        msg = format_missing_config_message(unconfigured, daemon, custom_path, only_rename)
        ui.print_log(msg)
        mail.send_error_email(error_message=msg)
        if exit_on_error:
            if not daemon and not runtime.daemon_enabled:
                sys.exit(1)
            raise FolderNotFoundError(msg)
        return 1

    return validate_folder_existence_and_permissions(required_folders, simulate=simulate, exit_on_error=exit_on_error)


# ── TMDB probability scorer ──────────────────────────────────────────────────


def compute_tmdb_match_probability(
    parsed_name: str | None,
    parsed_year: str | None,
    tmdb_title: str | None,
    tmdb_year: str | None,
) -> float:
    """Computes a match probability P ∈ [0.0, 1.0] between parsed metadata and a TMDB result.

    Combines string sequence similarity, token-set overlap, and year proximity.
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
    p_year_clean = (
        str(parsed_year).strip() if parsed_year and str(parsed_year).strip() not in ("None", "unknown", "") else None
    )
    t_year_clean = (
        str(tmdb_year).strip() if tmdb_year and str(tmdb_year).strip() not in ("None", "unknown", "") else None
    )

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


# ── Resolution / Quality parsing ─────────────────────────────────────────────


def parse_resolution_quality(
    resolution_ptn: str | None,
    quality_ptn: str | None,
    resolution_clean: str | None,
    quality_clean: str | None,
    file: str | Path,
    *,
    resolution_enabled: bool | None = None,
    quality_enabled: bool | None = None,
) -> tuple[str | None, str | None]:
    """Resolves the best available resolution and quality from multiple sources.

    ``resolution_enabled`` / ``quality_enabled`` parameters replace the old
    module-level ``RESOLUTION`` / ``QUALITY`` globals (B8 fix).
    When ``None``, the values are read from :data:`~src.runtime_config.runtime`.
    """
    from src import files

    res_on = runtime.resolution_enabled if resolution_enabled is None else resolution_enabled
    qual_on = runtime.quality_enabled if quality_enabled is None else quality_enabled

    if not res_on and not qual_on:
        return None, None

    # Resolution
    if resolution_ptn and str(resolution_ptn).strip():
        final_resolution: str | None = resolution_ptn
    elif resolution_clean and str(resolution_clean).strip():
        final_resolution = resolution_clean
    else:
        final_resolution = None

    # Quality
    if quality_ptn and str(quality_ptn).strip():
        final_quality: str | None = quality_ptn
    elif quality_clean and str(quality_clean).strip():
        final_quality = quality_clean
    else:
        final_quality = None

    # Scan file for missing values
    if final_resolution is None or final_quality is None:
        res_file, qual_file = files.get_file_quality_resolution(file)
        if final_resolution is None and res_file and str(res_file).strip():
            final_resolution = res_file
        if final_quality is None and qual_file and str(qual_file).strip():
            final_quality = qual_file

    return translate_resolution_to_name(final_resolution), final_quality


# ── Movie / TV show filename correction ──────────────────────────────────────


def correct_movie_filename(file: dict, ai_result: list | None = None) -> str | None:
    """Resolves and generates the corrected movie filename stem.

    B7 fix: ``year`` variable is no longer shadowed by ``ai_result``'s year
    before the French title lookup — the final year used is always
    ``tmdb_year`` when TMDB succeeds, regardless of the AI path taken.
    """
    from src import api, ui

    new_filename: str | None = None

    try:
        name: str = file["Parse"][0]
        year: str = file["Parse"][1]

        resolution, quality = parse_resolution_quality(
            file["Parse"][2], file["Parse"][3], file["Clean"][2], file["Clean"][3], file["Path"]
        )

        min_conf = config.TMDB_MIN_CONFIDENCE

        final_title: str | None = None
        final_year: str | None = None
        final_lang: str | None = None

        min_conf = config.TMDB_MIN_CONFIDENCE

        if ai_result is not None:
            # AI pre-resolved path
            ai_success, ai_title, ai_year, ai_lang = ai_result[0], ai_result[1], ai_result[2], ai_result[3]
            if ai_success:
                final_title = ai_title
                final_year = ai_year
                final_lang = ai_lang
                success = True
            else:
                success = False
        else:
            success = False
            best_tmdb = (False, None, None, None)

            # 1st TMDB attempt: parsed name + year
            s, t, ty, lg = api.api_call(name, year, "en-US", "movie")
            if s:
                prob = compute_tmdb_match_probability(name, year, t, ty)
                if prob >= min_conf:
                    success, final_title, final_year, final_lang = True, t, ty, lg
                    best_tmdb = (True, t, ty, lg)
                else:
                    best_tmdb = (True, t, ty, lg)

            # 2nd TMDB attempt: clean name + clean year
            if not success:
                c_name, c_year = file["Clean"][0], file["Clean"][1]
                s_c, t_c, ty_c, lg_c = api.api_call(c_name, c_year, "en-US", "movie")
                if s_c:
                    prob_c = compute_tmdb_match_probability(c_name, c_year, t_c, ty_c)
                    if prob_c >= min_conf or not runtime.ai_fallback_enabled:
                        success, final_title, final_year, final_lang = True, t_c, ty_c, lg_c
                        best_tmdb = (True, t_c, ty_c, lg_c)

            # 3rd: AI fallback
            if not success and runtime.ai_fallback_enabled:
                ai_res = api.gemini_api_call(file)
                if ai_res and ai_res[0]:
                    success, final_title, final_year, final_lang = True, ai_res[1], ai_res[2], ai_res[3]
                elif best_tmdb[0]:
                    success, final_title, final_year, final_lang = best_tmdb

        # French title lookup (B7 fix: uses final_year, not a shadowed local 'year')
        if success and final_lang in ("fr", "fr-FR"):
            lookup_name = name
            lookup_year = final_year or year
            s_fr, t_fr, y_fr, _ = api.api_call(lookup_name, lookup_year, "fr-FR", "movie")
            if s_fr:
                final_title = t_fr
                final_year = y_fr

        new_filename = generate_new_movie_filename(
            success,
            final_title,
            final_year,
            resolution,
            quality,
            resolution_enabled=runtime.resolution_enabled,
            quality_enabled=runtime.quality_enabled,
        )

    except Exception as e:
        failed_file = file.get("File", "Unknown File")
        error_message = f"Impossible to rename the following file: {failed_file}\n\nError logs: {e}\n"
        mail.send_error_email(error_message=error_message, affected_file=failed_file, exception=e)
        if runtime.verbose_enabled:
            from src import ui

            ui.print_log(error_message)
        new_filename = None

    return new_filename


def correct_tv_show_filename(
    file: dict,
    ai_result: list | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Resolves and generates the corrected TV show filename stem."""
    from src import api, ui

    new_filename: str | None = None
    season: str | None = None
    episode: str | None = None

    try:
        name: str = file["Parse"][0]

        s_raw, e_raw = parse_season_episode(file["Parse"][2], file["Parse"][3], file["File"])
        season, episode = format_season_and_episode(s_raw, e_raw)

        resolution, quality = parse_resolution_quality(
            file["Parse"][4], file["Parse"][5], file["Clean"][2], file["Clean"][3], file["Path"]
        )

        min_conf = config.TMDB_MIN_CONFIDENCE

        final_title: str | None = None
        final_lang: str | None = None

        if ai_result is not None:
            ai_success, ai_title, _, ai_lang = ai_result[0], ai_result[1], ai_result[2], ai_result[3]
            if ai_success:
                final_title = ai_title
                final_lang = ai_lang
                success = True
            else:
                success = False
        else:
            success = False
            best_tmdb = (False, None, None)

            # 1st TMDB attempt
            s, t, _, lg = api.api_call(name, None, "en-US", "tv")
            if s:
                prob = compute_tmdb_match_probability(name, None, t, None)
                if prob >= min_conf:
                    success, final_title, final_lang = True, t, lg
                    best_tmdb = (True, t, lg)
                else:
                    best_tmdb = (True, t, lg)

            # 2nd TMDB attempt: clean name
            if not success:
                c_name = file["Clean"][0]
                s_c, t_c, _, lg_c = api.api_call(c_name, None, "en-US", "tv")
                if s_c:
                    prob_c = compute_tmdb_match_probability(c_name, None, t_c, None)
                    if prob_c >= min_conf or not runtime.ai_fallback_enabled:
                        success, final_title, final_lang = True, t_c, lg_c
                        best_tmdb = (True, t_c, lg_c)

            # 3rd: AI fallback
            if not success and runtime.ai_fallback_enabled:
                ai_res = api.gemini_api_call(file)
                if ai_res and ai_res[0]:
                    success, final_title, final_lang = True, ai_res[1], ai_res[3]
                elif best_tmdb[0]:
                    success, final_title, final_lang = best_tmdb

        # French title lookup
        if success and final_lang in ("fr", "fr-FR"):
            lookup_name = name
            s_fr, t_fr, _, _ = api.api_call(lookup_name, None, "fr-FR", "tv")
            if s_fr:
                final_title = t_fr

        new_filename = generate_new_tvshow_filename(
            success,
            final_title,
            season,
            episode,
            resolution,
            quality,
            resolution_enabled=runtime.resolution_enabled,
            quality_enabled=runtime.quality_enabled,
        )

    except Exception as e:
        failed_file = file.get("File", "Unknown File")
        error_message = f"Impossible to rename the following file: {failed_file}\n\nError logs: {e}\n"
        mail.send_error_email(error_message=error_message, affected_file=failed_file, exception=e)
        if runtime.verbose_enabled:
            from src import ui

            ui.print_log(error_message)
        new_filename = None
        season = None
        episode = None

    return new_filename, season, episode


# ── DataFrame helpers ────────────────────────────────────────────────────────


def sort_media_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sorts the corrected filenames DataFrame by title, season, and episode."""
    if df.empty:
        return df
    return df.sort_values(by=["Corrected", "Season", "Episode"], ascending=[True, True, True], ignore_index=True)


def handle_conflicts_and_duplicates(df: pd.DataFrame, failed_files: list[dict]) -> pd.DataFrame:
    """Removes duplicate corrected filenames from *df*, appending them to *failed_files*."""
    if df.empty:
        return df

    check_for_duplicates = df[df.duplicated(subset=["Corrected"], keep=False)]
    if not check_for_duplicates.empty:
        conflicts = check_for_duplicates["Corrected"].unique()
        for conflict_name in conflicts:
            originals = check_for_duplicates[check_for_duplicates["Corrected"] == conflict_name]["Original"].tolist()
            for orig in originals:
                failed_files.append(
                    {"Original": orig, "Reason": f"Conflict: Multiple files resolve to '{conflict_name}'"}
                )
        df = df.drop_duplicates(subset=["Corrected"], keep=False)

    return df


def has_files_to_rename(data_table: pd.DataFrame) -> bool:
    """Returns True if the data table contains at least one file whose name changed.

    B13 fix: uses vectorised pandas comparison instead of ``iterrows()`` loop.
    """
    if data_table.empty:
        return False
    return bool((data_table["Original"] != data_table["Corrected"]).any())


# ── Main orchestration function ──────────────────────────────────────────────


def get_corrected_media_filenames(
    messy_data_table: pd.DataFrame,
    clean_data_table: pd.DataFrame,
) -> pd.DataFrame:
    """Processes all messy media files, querying TMDB and AI as needed."""
    from src import api, ui

    ui.print_log(f"\nAnalysing {len(messy_data_table)} files. Please wait...\n")

    new_clean_data_rows: list[dict] = []
    failed_files: list[dict] = []
    ai_results: dict[str, list] = {}

    if runtime.ai_fallback_enabled:
        ai_pending_items: list = []
        min_conf = config.TMDB_MIN_CONFIDENCE

        for _, file in messy_data_table.iterrows():
            m_type = file.get("Media")
            if m_type not in ("movie", "tv"):
                continue

            needs_fallback = False
            if m_type == "movie":
                p_name, p_year = file["Parse"][0], file["Parse"][1]
                s, t, y, _ = api.api_call(p_name, p_year, "en-US", "movie")
                prob = compute_tmdb_match_probability(p_name, p_year, t, y) if s else 0.0
                if not (s and prob >= min_conf):
                    c_name, c_year = file["Clean"][0], file["Clean"][1]
                    s_c, t_c, y_c, _ = api.api_call(c_name, c_year, "en-US", "movie")
                    prob_c = compute_tmdb_match_probability(c_name, c_year, t_c, y_c) if s_c else 0.0
                    if not (s_c and prob_c >= min_conf):
                        needs_fallback = True
            elif m_type == "tv":
                p_name = file["Parse"][0]
                s, t, _, _ = api.api_call(p_name, None, "en-US", "tv")
                prob = compute_tmdb_match_probability(p_name, None, t, None) if s else 0.0
                if not (s and prob >= min_conf):
                    c_name = file["Clean"][0]
                    s_c, t_c, _, _ = api.api_call(c_name, None, "en-US", "tv")
                    prob_c = compute_tmdb_match_probability(c_name, None, t_c, None) if s_c else 0.0
                    if not (s_c and prob_c >= min_conf):
                        needs_fallback = True

            if needs_fallback:
                ai_pending_items.append(file)

        if ai_pending_items:
            ui.print_log(f"Queuing {len(ai_pending_items)} files for AI batch fallback...\n")
            batch_size = 25
            for i in range(0, len(ai_pending_items), batch_size):
                chunk = ai_pending_items[i : i + batch_size]
                chunk_dicts = [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in chunk]
                batch_res = api.execute_ai_batch_with_failover(chunk_dicts)
                for file_obj, res in zip(chunk, batch_res):
                    ai_results[file_obj["File"]] = res

    for _, file in messy_data_table.iterrows():
        f_name = file["File"]
        ai_res = ai_results.get(f_name)

        if file["Media"] == "movie":
            corrected_name = correct_movie_filename(file, ai_result=ai_res)
            season, episode = None, None
        elif file["Media"] == "tv":
            corrected_name, season, episode = correct_tv_show_filename(file, ai_result=ai_res)
        else:
            ui.print_log(f"Ignored : {file['File']}\n")
            continue

        if corrected_name is None:
            failed_files.append({"Original": file["File"], "Reason": "API or parsing failed"})
        else:
            new_clean_data_rows.append(
                {
                    "Original": file["File"],
                    "Corrected": corrected_name,
                    "Path": file["Path"],
                    "Media": file["Media"],
                    "Season": season,
                    "Episode": episode,
                }
            )

    new_df = pd.DataFrame(new_clean_data_rows)
    df = pd.concat([clean_data_table, new_df], ignore_index=True) if not new_df.empty else clean_data_table

    df = sort_media_dataframe(df)
    df = handle_conflicts_and_duplicates(df, failed_files)

    ui.display_skipped_filenames(failed_files)

    return df


_UTILS_RUNTIME_MAP = {
    "RESOLUTION": "resolution_enabled",
    "QUALITY": "quality_enabled",
}

_UTILS_CONFIG_ATTRS = {
    "MOVIES_FOLDER",
    "TV_SHOWS_FOLDER",
    "NOT_SORTED_MEDIA_FILES_FOLDER",
}


class _UtilsModule(types.ModuleType):
    def __getattribute__(self, name: str):
        if name in _UTILS_RUNTIME_MAP:
            return getattr(runtime, _UTILS_RUNTIME_MAP[name])
        if name in _UTILS_CONFIG_ATTRS:
            return getattr(config, name, None)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value):
        if name in _UTILS_RUNTIME_MAP:
            setattr(runtime, _UTILS_RUNTIME_MAP[name], value)
            setattr(config, name, value)
        elif name in _UTILS_CONFIG_ATTRS:
            setattr(config, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _UtilsModule

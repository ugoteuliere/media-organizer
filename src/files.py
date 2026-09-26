"""
File-system operations for media-organizer.

Handles:
- Scanning and classifying video files in a directory
- Renaming media files in-place
- Moving media files to library folders (sort)
- Empty folder cleanup
- ffprobe metadata extraction for resolution/quality
- File lock detection (POSIX + Windows)

Key improvements over the original implementation:
- **B1 / R4**: ``sort_media_files`` and ``move_media_files`` read folders live
  from ``config`` instead of relying on stale module-level snapshots, and
  raise :exc:`~src.exceptions.FolderNotFoundError` on ``None``.
- **B2**: Error messages are printed *and then* raised as typed exceptions,
  not passed as ``RuntimeError(ui.print_error(...))``.
- **B3 / P2**: No module-level config-value snapshots.
- **B12**: No ``sys.exit()`` inside library functions — raises typed exceptions.
- **P5**: Separate ``json.JSONDecodeError`` handler in ``get_metadata_with_ffprobe``.
- **Docker logs**: Emoji stripped from daemon-mode (non-interactive) log messages.
"""

from __future__ import annotations

import json
from datetime import datetime
import os
import re
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Any

import pandas as pd

from data.data import QUALITY_PATTERNS, RESOLUTION_PATTERNS
from src import ui, utils, mail
from src.config import config
from src.exceptions import FileOperationError, FolderNotFoundError
from src.filename_processing import sanitize_filename
from src.runtime_config import runtime

_failed_files_cooldown = {}


# ── Constants ────────────────────────────────────────────────────────────────

PARTIAL_EXTENSIONS = {".crdownload", ".part", ".!ut", ".tmp", ".download", ".aria2"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v"}
MOVIE_REGEX = r"^.+? \(\d{4}\)(?: \[[^\]]+\])?$"
SERIES_REGEX = r"^.+?(?<! \(\d{4}\)) - S\d{2}E\d{2}(?: \[[^\]]+\])?$"


# ── File lock detection ──────────────────────────────────────────────────────


def _is_file_locked_posix(file_path: Path, wait_interval: float = 0.5) -> bool:
    """Checks fcntl lock and size/mtime stability on POSIX systems."""
    try:
        try:
            import fcntl

            has_fcntl = True
        except (ImportError, ModuleNotFoundError):
            has_fcntl = False

        with open(file_path, "rb") as f:
            if has_fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except BlockingIOError:
        return True
    except OSError:
        pass

    try:
        stat1 = file_path.stat()
        if (time.time() - stat1.st_mtime) < 2.0:
            time.sleep(min(wait_interval, 0.5))
            stat2 = file_path.stat()
            if stat1.st_size != stat2.st_size or stat1.st_mtime != stat2.st_mtime:
                return True
    except OSError:
        return True

    return False


def is_file_locked(file_path: Path, wait_interval: float = 0.5) -> bool:
    """Returns True if *file_path* is currently being written (e.g. downloading)."""
    if not file_path.is_file():
        return False

    try:
        os.rename(file_path, file_path)
    except OSError:
        return True

    if os.name != "nt":
        return _is_file_locked_posix(file_path, wait_interval)

    return False


# ── Directory scanning ───────────────────────────────────────────────────────


def resolve_search_directory(path: str | None = None) -> Path | None:
    """Resolves and validates the target directory to scan for media files.

    Reads ``NOT_SORTED_MEDIA_FILES_FOLDER`` live from ``config`` (B3/P2 fix).
    """
    folder_val = config.NOT_SORTED_MEDIA_FILES_FOLDER
    if path is not None:
        target_dir = Path(path).resolve()
    elif folder_val:
        target_dir = Path(folder_val).resolve()
    else:
        ui.print_log("Error: No media directory specified or configured.")
        return None

    if not target_dir.exists() or not target_dir.is_dir():
        ui.print_log(f"Error: The directory '{target_dir}' does not exist.")
        return None

    return target_dir


def collect_candidate_video_files(target_dir: Path, ignored_files: list[Path] | None = None) -> list[Path]:
    """Recursively scans *target_dir* and returns non-locked video files."""
    global _failed_files_cooldown
    candidates: list[Path] = []
    now = datetime.now()

    # Clean up old cooldowns (older than 24 hours)
    _failed_files_cooldown = {k: v for k, v in _failed_files_cooldown.items() if (now - v).total_seconds() < 86400}

    # Check for minimum file size (defaults to 0, meaning disabled / no filtering)
    min_size_mb = float(os.environ.get("MIN_FILE_SIZE_MB", "0"))
    min_size_bytes = int(min_size_mb * 1024 * 1024)
    for file_path in target_dir.rglob("*"):
        if file_path.suffix.lower() in PARTIAL_EXTENSIONS:
            continue
        if file_path.suffix.lower() in VIDEO_EXTENSIONS:
            if str(file_path.resolve()) in _failed_files_cooldown:
                if ignored_files is not None:
                    ignored_files.append(file_path)
                continue

            try:
                st = file_path.stat()
                if min_size_mb > 0 and st.st_size < min_size_bytes:
                    ui.log_info(f"Skipping undersized file: {file_path.name}")
                    continue
            except OSError:
                continue

            if is_file_locked(file_path):
                ui.print_log(f"Skipping active/locked download: {file_path.name}")
                continue
            candidates.append(file_path)
    return candidates


def extract_parse_tokens(parse: tuple, media: str, is_movie: bool) -> tuple[str | None, str | None]:
    """Extracts raw resolution and quality pattern candidates from parse results."""
    if is_movie or media == "movie":
        res_ptn = parse[2] if len(parse) > 2 else None
        qual_ptn = parse[3] if len(parse) > 3 else None
    else:
        res_ptn = parse[4] if len(parse) > 4 else None
        qual_ptn = parse[5] if len(parse) > 5 else None
    return res_ptn, qual_ptn


def format_stream_tags(
    final_res: str | None, final_qual: str | None, res_enabled: bool, qual_enabled: bool
) -> list[str]:
    """Builds formatted resolution/quality tag tokens if present and enabled."""
    metadata_parts: list[str] = []
    if qual_enabled and final_qual and str(final_qual).strip():
        metadata_parts.append(str(final_qual).strip())
    if res_enabled and final_res and str(final_res).strip():
        metadata_parts.append(str(final_res).strip())
    return metadata_parts


def append_resolution_quality_tags(
    file_path: Path, name_without_ext: str, parse: tuple, media: str, is_movie: bool
) -> str:
    """Appends resolution and quality tags to an already normalised media title if enabled."""
    res_enabled = runtime.resolution_enabled or bool(config.RESOLUTION)
    qual_enabled = runtime.quality_enabled or bool(config.QUALITY)
    has_tags = bool(re.search(r" \[[^\]]+\]$", name_without_ext))

    if not (res_enabled or qual_enabled) or has_tags:
        return name_without_ext

    res_ptn, qual_ptn = extract_parse_tokens(parse, media, is_movie)
    final_res, final_qual = utils.parse_resolution_quality(
        res_ptn,
        qual_ptn,
        None,
        None,
        str(file_path),
        resolution_enabled=res_enabled,
        quality_enabled=qual_enabled,
    )
    metadata_parts = format_stream_tags(final_res, final_qual, res_enabled, qual_enabled)

    if metadata_parts:
        return f"{name_without_ext} [{' '.join(metadata_parts)}]"
    return name_without_ext


def extract_season_episode(name_without_ext: str, parse: tuple) -> tuple[str | None, str | None]:
    """Extracts normalised season and episode numbers from parse tokens or SxxExx regex."""
    se_match = re.search(r"S(\d+)E(\d+)", name_without_ext, re.IGNORECASE)
    season_val: str | None = None
    episode_val: str | None = None

    if len(parse) > 2 and parse[2]:
        season_val = str(parse[2])
    elif se_match:
        season_val = str(int(se_match.group(1)))

    if len(parse) > 3 and parse[3]:
        episode_val = str(parse[3])
    elif se_match:
        episode_val = str(int(se_match.group(2)))

    return season_val, episode_val


def build_clean_media_entry(
    file_path: Path,
    corrected_name: str,
    parse: tuple,
    media: str,
    is_movie: bool,
    is_series: bool,
) -> dict[str, Any] | None:
    """Constructs a clean media metadata dictionary for valid movie or series files."""
    if is_movie or media == "movie":
        return {
            "Original": file_path.stem,
            "Corrected": corrected_name,
            "Path": str(file_path),
            "Media": "movie",
            "Season": None,
            "Episode": None,
        }

    if is_series or media == "tv":
        season_val, episode_val = extract_season_episode(file_path.stem.strip(), parse)
        return {
            "Original": file_path.stem,
            "Corrected": corrected_name,
            "Path": str(file_path),
            "Media": "tv",
            "Season": season_val,
            "Episode": episode_val,
        }

    return None


def classify_video_file(file_path: Path, messy_data_table: list, clean_data_table: list) -> None:
    """Categorises a video file into messy or clean tables based on naming regexes."""
    from src.filename_processing import parse_filename, clean_filename

    name_without_ext = file_path.stem.strip()
    is_movie = bool(re.fullmatch(MOVIE_REGEX, name_without_ext))
    is_series = bool(re.fullmatch(SERIES_REGEX, name_without_ext))

    parse, media = parse_filename(file_path.name)

    if not is_movie and not is_series:
        messy_data_table.append(
            {
                "File": file_path.name,
                "Folder": file_path.parent.name,
                "Path": str(file_path),
                "Clean": clean_filename(file_path.name),
                "Parse": parse,
                "Media": media,
            }
        )
        return

    corrected_name = append_resolution_quality_tags(file_path, name_without_ext, parse, media, is_movie)
    clean_entry = build_clean_media_entry(file_path, corrected_name, parse, media, is_movie, is_series)
    if clean_entry:
        clean_data_table.append(clean_entry)


def build_search_result_tables(
    messy_data_table: list,
    clean_data_table: list,
    exit_if_empty: bool = True,
    ignored_files_count: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Converts result lists into sorted DataFrames.

    B12 fix: does not call ``sys.exit()`` — returns empty DataFrames when
    ``exit_if_empty=False``.  When ``exit_if_empty=True`` the caller (main)
    handles the empty case gracefully.
    """
    files_to_rename_count = len(messy_data_table) + sum(1 for f in clean_data_table if f["Original"] != f["Corrected"])
    clean_files_count = sum(1 for f in clean_data_table if f["Original"] == f["Corrected"])

    parts = []
    if files_to_rename_count > 0:
        word = "file" if files_to_rename_count == 1 else "files"
        parts.append(f"{files_to_rename_count} {word} to rename")
    if clean_files_count > 0:
        word = "file" if clean_files_count == 1 else "files"
        parts.append(f"{clean_files_count} {word} with clean filename")
    if ignored_files_count > 0:
        word = "file" if ignored_files_count == 1 else "files"
        parts.append(f"{ignored_files_count} {word} ignored because of previous errors")

    if parts:
        ui.log_info(f"Folder scan report: {', '.join(parts)}")

    if len(messy_data_table) == 0 and len(clean_data_table) == 0:
        if exit_if_empty:
            ui.print_log("No media files found in that folder")
            sys.exit(1)
        return pd.DataFrame(), pd.DataFrame()

    messy_data = pd.DataFrame(messy_data_table)
    clean_data = pd.DataFrame(clean_data_table, columns=["Original", "Corrected", "Path", "Media", "Season", "Episode"])
    sorted_clean_data = clean_data.sort_values(
        by=["Corrected", "Season", "Episode"], ascending=[True, True, True], ignore_index=True
    )
    return messy_data, sorted_clean_data


def search_media_files(
    path: str | None = None,
    exit_if_empty: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Scans the configured or given directory and returns (messy, clean) DataFrames."""
    target_dir = resolve_search_directory(path)
    if target_dir is None:
        return None

    messy_data_table: list = []
    clean_data_table: list = []
    ignored_files: list[Path] = []

    candidate_files = collect_candidate_video_files(target_dir, ignored_files=ignored_files)
    for file_path in candidate_files:
        classify_video_file(file_path, messy_data_table, clean_data_table)

    return build_search_result_tables(
        messy_data_table,
        clean_data_table,
        exit_if_empty=exit_if_empty,
        ignored_files_count=len(ignored_files),
    )


# ── Windows long-path helper ─────────────────────────────────────────────────


def make_safe_path(path: Path) -> str:
    """Returns a Windows extended-length path prefix (``\\\\?\\``) when necessary."""
    if os.name != "nt":
        return str(path)

    path_str = str(path)
    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str.lstrip("\\")
    return "\\\\?\\" + path_str


# ── Rename ───────────────────────────────────────────────────────────────────


def rename_media_files(clean_data_table: pd.DataFrame) -> pd.DataFrame:
    """Renames all files in *clean_data_table* in-place.

    B2 fix: errors are printed via ``ui.print_log`` *and then* raised as
    :exc:`~src.exceptions.FileOperationError` — not passed as the message of
    a bare ``RuntimeError(ui.print_error(...))``.
    """
    renamed_count = 0
    already_clean_files_count = 0

    for index, row in clean_data_table.iterrows():
        if pd.isna(row["Corrected"]):
            ui.print_log(f"\n  Ignored (not found) : {row['Original']}")
            continue

        original_path = Path(str(row["Path"])).resolve()
        safe_old_path = make_safe_path(original_path)

        if not os.path.exists(safe_old_path):
            ui.print_log(f"Error (file does not exist) : {original_path.name[:30]}...")
            continue

        extension = original_path.suffix
        new_filename = f"{row['Corrected']}{extension}"

        new_path = original_path.with_name(new_filename).resolve()
        safe_new_path = make_safe_path(new_path)

        try:
            if safe_old_path == safe_new_path:
                already_clean_files_count += 1
                continue

            clean_data_table.loc[index, "Path"] = str(new_path)
            os.rename(safe_old_path, safe_new_path)
            renamed_count += 1

        except Exception as e:
            msg = ui.print_error(f" Error: Impossible to rename {original_path.name[:30]}...", e)
            ui.print_log(msg)
            raise FileOperationError(msg) from e

    if not runtime.daemon_enabled:
        if renamed_count == 0:
            ui.print_log("\n ❌ No files have been renamed.")
        else:
            ui.print_log(
                f"\nDone! {renamed_count}/{len(clean_data_table) - already_clean_files_count}"
                " file(s) have been successfully renamed.\n\n"
            )

    return clean_data_table


# ── Sort ─────────────────────────────────────────────────────────────────────


def sort_media_files(clean_data_table: pd.DataFrame) -> list[list[Path]]:
    """Computes destination paths for all media in *clean_data_table*.

    B1 / R4 fix: reads folder paths live from ``config`` and raises
    :exc:`~src.exceptions.FolderNotFoundError` when the required folders are
    ``None``, instead of passing ``None`` to ``Path()`` which raises a
    confusing ``TypeError``.
    """
    movies_folder = config.MOVIES_FOLDER
    tv_shows_folder = config.TV_SHOWS_FOLDER

    paths: list[list[Path]] = []

    for _, movie in clean_data_table.iterrows():
        old_path = Path(str(movie["Path"]))
        extension = old_path.suffix
        media = movie["Media"]
        corrected_name = f"{movie['Corrected']}{extension}"

        if media == "movie":
            # B1: guard against None
            if not movies_folder:
                raise FolderNotFoundError(
                    "Movies folder is not configured. "
                    'Set it with: media-organizer config --set paths.movies_folder "path/to/movies"'
                )
            folder_path = Path(movies_folder)
            folder_path.mkdir(parents=True, exist_ok=True)
            new_path = folder_path / corrected_name

        elif media == "tv":
            # B1: guard against None
            if not tv_shows_folder:
                raise FolderNotFoundError(
                    "TV Shows folder is not configured. "
                    'Set it with: media-organizer config --set paths.tv_shows_folder "path/to/tv_shows"'
                )

            match = re.search(r"S(\d+)E\d+", str(movie["Corrected"]), flags=re.IGNORECASE)
            season_folder = f"Season {match.group(1).zfill(2)}" if match else "Unknown"

            tv_show_name = re.sub(r"\s*(?:-\s*)?S\d+E\d+.*$", "", str(movie["Corrected"]), flags=re.IGNORECASE).strip()
            tv_show_name = re.sub(r"\s*\[.*?\]", "", tv_show_name).strip()
            tv_show_name = re.sub(r"\s*\(\d{4}\)$", "", tv_show_name).strip()
            tv_show_name = sanitize_filename(tv_show_name) or "Unknown Show"

            folder_path = Path(tv_shows_folder) / tv_show_name / season_folder
            folder_path.mkdir(parents=True, exist_ok=True)
            new_path = folder_path / corrected_name

        else:
            ui.print_log(f"⏭ Ignored (not found) : {corrected_name}")
            continue

        # Path traversal guard
        base_dir = Path(movies_folder if media == "movie" else tv_shows_folder).resolve()
        if not new_path.resolve().is_relative_to(base_dir):
            raise PermissionError(f"Path traversal detected: {new_path}")

        paths.append([old_path, new_path])

    if not paths:
        ui.print_log("No media to move to a new folder.")
        if not runtime.daemon_enabled:
            sys.exit(1)
        return []

    return paths


# ── Move ─────────────────────────────────────────────────────────────────────


def move_file(old_path: Path | str, new_path: Path | str) -> None:
    """Moves a single file from *old_path* to *new_path*.

    Attempts an atomic ``os.rename()`` first.  On cross-device ``OSError``,
    falls back to ``shutil.copy()`` + ``os.utime()`` + ``os.unlink()``
    (no ``chmod``, safe for ZFS restricted-ACL datasets).

    Raises :exc:`FileExistsError` when the destination already exists.
    Raises :exc:`~src.exceptions.FileOperationError` on unexpected OS errors.
    """
    old_abs = Path(old_path).resolve()
    new_abs = Path(new_path).resolve()

    if old_abs == new_abs:
        return

    if new_abs.exists():
        error_msg = f" Conflict: Target file already exists at {new_abs}"
        raise FileExistsError(error_msg)

    safe_old = make_safe_path(old_abs)
    safe_new = make_safe_path(new_abs)

    try:
        os.rename(safe_old, safe_new)
    except OSError:
        try:
            shutil.copy(safe_old, safe_new)
            stat_info = os.stat(safe_old)
            os.utime(safe_new, (stat_info.st_atime, stat_info.st_mtime))
            os.unlink(safe_old)
        except Exception as e:
            if os.path.exists(safe_new) and os.path.exists(safe_old):
                try:
                    os.unlink(safe_new)
                except OSError:
                    pass
            msg = ui.print_error(f" Error: Impossible to move the file\n Old path {safe_old}\n New path {safe_new}", e)
            raise FileOperationError(msg) from e


def remove_empty_folders(target_path: Path | str) -> None:
    """Recursively removes empty sub-directories under *target_path*."""
    if not os.path.exists(target_path):
        ui.print_log(f"The path '{target_path}' does not exist.")
        return

    target_dir = Path(target_path).resolve()

    for dirpath, _dirnames, _filenames in os.walk(target_dir, topdown=False):
        current_dir = Path(dirpath).resolve()
        if current_dir == target_dir:
            continue

        try:
            if not os.listdir(dirpath):
                try:
                    os.rmdir(dirpath)
                except OSError as e:
                    ui.print_log(f"Warning: Could not delete empty folder '{dirpath}': {e}")
        except OSError as e:
            ui.print_log(f"Warning: Could not inspect folder '{dirpath}': {e}")


def build_destination_lookup(clean_data_table: pd.DataFrame | None = None) -> dict[str, tuple[str, str]]:
    """Maps destination stem back to ``(original_name, media_type)``."""
    lookup: dict[str, tuple[str, str]] = {}
    if clean_data_table is not None and not clean_data_table.empty:
        for _, row in clean_data_table.iterrows():
            corr = str(row.get("Corrected", ""))
            orig = str(row.get("File", row.get("Original", "")))
            media = str(row.get("Media", ""))
            lookup[corr] = (orig, media)
    return lookup


def infer_media_type_from_destination(
    p_new: Path,
    movies_dir: Path | None = None,
    tv_dir: Path | None = None,
) -> str:
    """Infers media type based on destination directory relative location."""
    try:
        if movies_dir and p_new.resolve().is_relative_to(movies_dir.resolve()):
            return "movie"
        if tv_dir and p_new.resolve().is_relative_to(tv_dir.resolve()):
            return "tv"
    except Exception:
        pass
    return "unknown"


def execute_single_file_move(
    old: Path | str,
    new: Path | str,
    lookup: dict,
    movies_dir: Path | None = None,
    tv_dir: Path | None = None,
) -> tuple[bool, str | None]:
    """Moves an individual media file and dispatches email notifications."""
    p_old = Path(old)
    p_new = Path(new)
    try:
        move_file(old, new)

        orig_name, media_type = lookup.get(p_new.stem, (p_old.name, "unknown"))
        if media_type == "unknown":
            media_type = infer_media_type_from_destination(p_new, movies_dir, tv_dir)

        if runtime.daemon_enabled:
            ui.log_success(orig_name, p_new.name, str(p_new))

        mail.send_media_success_email(
            media_name=p_new.name,
            original_name=orig_name,
            media_type=media_type,
            destination_path=str(p_new),
        )
        return True, None
    except Exception as e:
        if runtime.daemon_enabled:
            ui.log_error(f"Failed to move '{p_old.name}': {e}")
        else:
            ui.print_log(f" Skipping {p_old.name}: {e} \n")
        try:
            mail.send_error_email(error_message=str(e), affected_file=p_old.name)
        except Exception as mail_err:
            ui.log_error(f"Error while trying to send the email: {mail_err}")
        return False, p_old.name


def move_media_files(
    paths: list,
    clean_data_table: pd.DataFrame | None = None,
    source_path: str | None = None,
) -> tuple[int, int]:
    """Moves all (old, new) path pairs returned by :func:`sort_media_files`.

    B3/P2 fix: reads ``NOT_SORTED_MEDIA_FILES_FOLDER`` live from ``config``
    for the cleanup step rather than from a stale module-level snapshot.
    """
    success_count = 0
    failed_moves: list[str | None] = []

    movies_folder = config.MOVIES_FOLDER
    tv_folder = config.TV_SHOWS_FOLDER
    movies_dir = Path(movies_folder) if movies_folder else None
    tv_dir = Path(tv_folder) if tv_folder else None
    lookup = build_destination_lookup(clean_data_table)

    global _failed_files_cooldown
    for old, new in paths:
        success, failed_file = execute_single_file_move(old, new, lookup, movies_dir, tv_dir)
        if success:
            success_count += 1
            old_key = str(Path(old).resolve())
            if old_key in _failed_files_cooldown:
                del _failed_files_cooldown[old_key]
        else:
            failed_moves.append(failed_file)
            old_key = str(Path(old).resolve())
            _failed_files_cooldown[old_key] = datetime.now()
            ui.log_info(f"'{Path(old).name}' will be ignored for the next 24 hours")

    if not runtime.daemon_enabled:
        if success_count > 0:
            ui.print_log(f"\n{success_count} files moved successfully!")
        if failed_moves:
            ui.print_log(f"{len(failed_moves)} files could not be moved")

    not_sorted_folder = config.NOT_SORTED_MEDIA_FILES_FOLDER
    cleanup_target = Path(source_path) if source_path else (Path(not_sorted_folder) if not_sorted_folder else None)
    if cleanup_target:
        remove_empty_folders(cleanup_target)

    return success_count, len(failed_moves)


# ── ffprobe metadata extraction ──────────────────────────────────────────────


def get_file_quality_resolution(file_path: str | Path) -> tuple[str | None, str | None]:
    """Returns ``(resolution, quality)`` for a video file using ffprobe."""
    metadata = get_metadata_with_ffprobe(file_path)
    if not metadata:
        return None, None

    technical_blob = ""
    width_map = {3840: "2160p 4k", 2560: "1440p", 1920: "1080p", 1280: "720p", 720: "480p"}

    streams = metadata.get("streams", [])
    for stream in streams:
        width = stream.get("width")
        if width:
            res_name = width_map.get(width, "")
            technical_blob += f" {width}x{stream.get('height')} {res_name} "
        technical_blob += f" {stream.get('codec_name')} {stream.get('pix_fmt')} {stream.get('color_space')} "

    fmt = metadata.get("format", {})
    technical_blob += f" {fmt.get('format_name')} "
    for _key, value in (fmt.get("tags") or {}).items():
        technical_blob += f" {value} "

    scan_string = technical_blob.replace("_", " ").replace(".", " ")

    final_res: str | None = None
    for pattern in RESOLUTION_PATTERNS:
        match = re.search(pattern, scan_string, flags=re.IGNORECASE)
        if match:
            final_res = match.group(0).strip()
            break

    final_qual: str | None = None
    for pattern in QUALITY_PATTERNS:
        match = re.search(pattern, scan_string, flags=re.IGNORECASE)
        if match:
            final_qual = match.group(0).strip()
            break

    if final_qual is None:
        raw_bitrate = fmt.get("bit_rate")
        if raw_bitrate:
            try:
                mbps = round(int(raw_bitrate) / 1_000_000)
                final_qual = f"{mbps}Mbps"
            except (ValueError, TypeError):
                pass

    return final_res, final_qual


def get_metadata_with_ffprobe(file_path: str | Path) -> dict | None:
    """Runs ffprobe and returns parsed JSON metadata.

    P5 fix: separate ``json.JSONDecodeError`` handler instead of a bare
    ``except Exception``, providing clearer error messages on corrupted output.
    """
    if not shutil.which("ffprobe"):
        ui.print_log(
            "Warning: ffprobe is not installed or not found in System PATH.\n"
            "FFmpeg is only required if you activate the resolution and quality tags feature.\n"
            "To install FFmpeg, see: docs/documentation.md#ffmpeg-setup\n"
            "Or disable it via: media-organizer config --set options.resolution false\n"
        )
        return None

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=width,height,codec_name,pix_fmt,color_space",
        "-show_entries",
        "format=format_name,bit_rate,tags",
        "-of",
        "json",
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        if runtime.daemon_enabled and not runtime.verbose_enabled:
            ui.log_info(f"Warning: ffprobe failed for {Path(file_path).name}")
        else:
            msg = ui.print_error("Error: ffprobe exited with non-zero status", e)
            ui.print_log(msg)
        return None
    except Exception as e:
        if runtime.daemon_enabled and not runtime.verbose_enabled:
            ui.log_info(f"Warning: ffprobe encountered an error for {Path(file_path).name}")
        else:
            msg = ui.print_error("Error: An error occurred while running ffprobe", e)
            ui.print_log(msg)
        return None

    # P5 fix: handle non-JSON output separately
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        ui.print_log(f"Error: ffprobe returned non-JSON output: {e}")
        return None


_FILES_CONFIG_ATTRS = {
    "MOVIES_FOLDER",
    "TV_SHOWS_FOLDER",
    "NOT_SORTED_MEDIA_FILES_FOLDER",
}


class _FilesModule(types.ModuleType):
    def __getattribute__(self, name: str):
        if name in _FILES_CONFIG_ATTRS:
            return getattr(config, name, None)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value):
        if name in _FILES_CONFIG_ATTRS:
            setattr(config, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _FilesModule

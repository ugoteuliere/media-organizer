from __future__ import annotations
from typing import Optional, List, Dict, Tuple, Any
from pathlib import Path
import pandas as pd
import re
import sys
import shutil
import os
import subprocess
import json
from src import ui, utils, mail
from data.data import QUALITY_PATTERNS, RESOLUTION_PATTERNS

from src.config import config
MOVIES_FOLDER = getattr(config, 'MOVIES_FOLDER', None)
TV_SHOWS_FOLDER = getattr(config, 'TV_SHOWS_FOLDER', None)
NOT_SORTED_MEDIA_FILES_FOLDER = getattr(config, 'NOT_SORTED_MEDIA_FILES_FOLDER', None)

PARTIAL_EXTENSIONS = {'.crdownload', '.part', '.!ut', '.tmp', '.download', '.aria2'}

def is_file_locked(file_path: Path) -> bool:
    """Check if a file is currently being written to by another process (e.g. downloading)."""
    if not file_path.is_file():
        return False
    try:
        os.rename(file_path, file_path)
        return False
    except OSError:
        return True

VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m4v'}
MOVIE_REGEX = r"^.+? \(\d{4}\)(?: \[[^\]]+\])?$"
SERIES_REGEX = r"^.+?(?<! \(\d{4}\)) - S\d{2}E\d{2}(?: \[[^\]]+\])?$"

def resolve_search_directory(path=None) -> Optional[Path]:
    """Resolves and validates the target directory to scan for media files."""
    folder_val = NOT_SORTED_MEDIA_FILES_FOLDER or getattr(config, 'NOT_SORTED_MEDIA_FILES_FOLDER', None)
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

def collect_candidate_video_files(target_dir: Path) -> List[Path]:
    """Recursively scans target_dir and returns video files excluding locked or partial downloads."""
    candidates = []
    for file_path in target_dir.rglob('*'):
        if file_path.suffix.lower() in PARTIAL_EXTENSIONS:
            continue
        if file_path.suffix.lower() in VIDEO_EXTENSIONS:
            if is_file_locked(file_path):
                ui.print_log(f"Skipping active/locked download: {file_path.name}")
                continue
            candidates.append(file_path)
    return candidates

def extract_parse_tokens(parse: tuple, media: str, is_movie: bool) -> Tuple[Optional[str], Optional[str]]:
    """Extracts raw resolution and quality pattern candidates from parse results."""
    if is_movie or media == "movie":
        res_ptn = parse[2] if len(parse) > 2 else None
        qual_ptn = parse[3] if len(parse) > 3 else None
    else:
        res_ptn = parse[4] if len(parse) > 4 else None
        qual_ptn = parse[5] if len(parse) > 5 else None
    return res_ptn, qual_ptn

def format_stream_tags(final_res: Optional[str], final_qual: Optional[str], res_enabled: bool, qual_enabled: bool) -> List[str]:
    """Builds formatted resolution/quality tag tokens if present and enabled."""
    metadata_parts: List[str] = []
    if qual_enabled and final_qual:
        cleaned_qual = str(final_qual).strip()
        if cleaned_qual:
            metadata_parts.append(cleaned_qual)
    if res_enabled and final_res:
        cleaned_res = str(final_res).strip()
        if cleaned_res:
            metadata_parts.append(cleaned_res)
    return metadata_parts

def append_resolution_quality_tags(file_path: Path, name_without_ext: str, parse: tuple, media: str, is_movie: bool) -> str:
    """Appends resolution and quality tags to an already normalized media title if enabled."""
    res_enabled = bool(getattr(utils, 'RESOLUTION', False) or getattr(ui, 'RESOLUTION_ENABLED', False) or getattr(config, 'RESOLUTION', False))
    qual_enabled = bool(getattr(utils, 'QUALITY', False) or getattr(ui, 'QUALITY_ENABLED', False) or getattr(config, 'QUALITY', False))
    has_tags = bool(re.search(r" \[[^\]]+\]$", name_without_ext))

    if not (res_enabled or qual_enabled) or has_tags:
        return name_without_ext

    if res_enabled:
        utils.RESOLUTION = True
    if qual_enabled:
        utils.QUALITY = True

    res_ptn, qual_ptn = extract_parse_tokens(parse, media, is_movie)
    final_res, final_qual = utils.parse_resolution_quality(
        res_ptn, qual_ptn, None, None, str(file_path)
    )
    metadata_parts = format_stream_tags(final_res, final_qual, res_enabled, qual_enabled)

    if metadata_parts:
        return f"{name_without_ext} [{' '.join(metadata_parts)}]"
    return name_without_ext

def extract_season_episode(name_without_ext: str, parse: tuple) -> Tuple[Optional[str], Optional[str]]:
    """Extracts normalized season and episode numbers from parsed tokens or SxxExx regex."""
    se_match = re.search(r'S(\d+)E(\d+)', name_without_ext, re.IGNORECASE)
    season_val = None
    episode_val = None

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
    is_series: bool
) -> Optional[Dict[str, Any]]:
    """Constructs a clean media metadata dictionary for valid movie or series files."""
    if is_movie or media == "movie":
        return {
            'Original': file_path.stem,
            'Corrected': corrected_name,
            'Path': str(file_path),
            'Media': 'movie',
            'Season': None,
            'Episode': None
        }

    if is_series or media == "tv":
        season_val, episode_val = extract_season_episode(file_path.stem.strip(), parse)
        return {
            'Original': file_path.stem,
            'Corrected': corrected_name,
            'Path': str(file_path),
            'Media': 'tv',
            'Season': season_val,
            'Episode': episode_val
        }

    return None

def classify_video_file(file_path: Path, messy_data_table: list, clean_data_table: list):
    """Categorizes a video file into messy or clean tables based on standardized naming regexes."""
    name_without_ext = file_path.stem.strip()
    is_movie = bool(re.fullmatch(MOVIE_REGEX, name_without_ext))
    is_series = bool(re.fullmatch(SERIES_REGEX, name_without_ext))

    parse, media = utils.parse_filename(file_path.name)

    if not is_movie and not is_series:
        messy_data_table.append({
            'File': file_path.name,
            'Folder': file_path.parent.name,
            'Path': str(file_path),
            'Clean': utils.clean_filename(file_path.name),
            'Parse': parse,
            'Media': media
        })
        return

    corrected_name = append_resolution_quality_tags(file_path, name_without_ext, parse, media, is_movie)
    clean_entry = build_clean_media_entry(file_path, corrected_name, parse, media, is_movie, is_series)
    if clean_entry:
        clean_data_table.append(clean_entry)

def build_search_result_tables(messy_data_table: list, clean_data_table: list, exit_if_empty: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Summarizes scan findings and converts result lists into sorted DataFrames."""
    if len(messy_data_table) == 0 and len(clean_data_table) == 0:
        if exit_if_empty:
            ui.print_log("❌ No media files found in that folder")
            sys.exit(1)
        return pd.DataFrame(), pd.DataFrame()

    files_to_rename_count = len(messy_data_table) + sum(1 for f in clean_data_table if f['Original'] != f['Corrected'])
    clean_files_count = sum(1 for f in clean_data_table if f['Original'] == f['Corrected'])
    ui.print_log(f"\n📂 Folder scan report:\n - {files_to_rename_count} files to rename\n - {clean_files_count} files with clean filename\n")

    messy_data = pd.DataFrame(messy_data_table)
    clean_data = pd.DataFrame(
        clean_data_table,
        columns=['Original', 'Corrected', 'Path', 'Media', 'Season', 'Episode']
    )
    sorted_clean_data = clean_data.sort_values(
        by=['Corrected', 'Season', 'Episode'],
        ascending=[True, True, True],
        ignore_index=True
    )
    return messy_data, sorted_clean_data

def search_media_files(path=None, exit_if_empty=True):
    target_dir = resolve_search_directory(path)
    if target_dir is None:
        return None

    messy_data_table = []
    clean_data_table = []

    candidate_files = collect_candidate_video_files(target_dir)
    for file_path in candidate_files:
        classify_video_file(file_path, messy_data_table, clean_data_table)

    return build_search_result_tables(messy_data_table, clean_data_table, exit_if_empty=exit_if_empty)

def make_safe_path(path: Path) -> str:
    if os.name != 'nt':
        return str(path)

    path_str = str(path)

    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str.lstrip("\\")
    else:
        return "\\\\?\\" + path_str

def rename_media_files(clean_data_table):
    renamed_count = 0
    already_clean_files_count = 0

    for index, row in clean_data_table.iterrows():

        if pd.isna(row['Corrected']):
            ui.print_log(f"\n⏭   Ignored (not found) : {row['Original']}")
            continue
            
        original_path = Path(str(row['Path'])).resolve()
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
                
            clean_data_table.loc[index, 'Path'] = str(new_path)
            os.rename(safe_old_path, safe_new_path)
            
            renamed_count += 1
            
        except Exception as e:
            raise RuntimeError(ui.print_error(f" ❌ Error: Impossible to rename {original_path.name[:30]}...",e))

    if renamed_count == 0:
        ui.print_log("\n ❌ No files have been renamed.")
    else:
        ui.print_log(f"\n🎉 Done ! {renamed_count}/{len(clean_data_table)-already_clean_files_count} file(s) have been successfully renamed.\n\n")
    
    return clean_data_table

def sort_media_files(clean_data_table):
    paths = []

    for index, movie in clean_data_table.iterrows():
        old_path = Path(str(movie['Path']))
        extension = old_path.suffix
        media = movie['Media']
        
        corrected_name = f"{movie['Corrected']}{extension}"
        
        if media == "movie":
            folder_path = Path(MOVIES_FOLDER)
            folder_path.mkdir(parents=True, exist_ok=True)
            new_path = folder_path / corrected_name
            
        elif media == "tv":
            match = re.search(r'S(\d+)E\d+', str(movie['Corrected']), flags=re.IGNORECASE)

            if match:
                season_number = match.group(1) 
                season_folder = f"Season {season_number.zfill(2)}" 
            else:
                season_folder = "Unknown" 

            tv_show_name = re.sub(r'\s*(?:-\s*)?S\d+E\d+.*$', '', str(movie['Corrected']), flags=re.IGNORECASE).strip()
            tv_show_name = re.sub(r'\s*\[.*?\]', '', tv_show_name).strip()
            tv_show_name = re.sub(r'\s*\(\d{4}\)$', '', tv_show_name).strip()
            tv_show_name = utils.sanitize_filename(tv_show_name) or "Unknown Show"

            folder_path = Path(TV_SHOWS_FOLDER) / tv_show_name / season_folder
            folder_path.mkdir(parents=True, exist_ok=True)
            new_path = folder_path / corrected_name
            
        else:
            ui.print_log(f"⏭ Ignored (not found) : {corrected_name}")
            continue

        base_dir = Path(MOVIES_FOLDER if media == "movie" else TV_SHOWS_FOLDER).resolve()
        if not new_path.resolve().is_relative_to(base_dir):
            raise PermissionError(f"Path traversal detected: {new_path}")

        paths.append([old_path, new_path])

    if not paths:
        ui.print_log("No media to move to a new folder.")
        sys.exit(1)

    return paths

def move_file(old_path, new_path):
    old_abs = old_path.resolve()
    new_abs = new_path.resolve()

    if old_abs == new_abs:
        return

    if new_abs.exists():
        error_msg = f" ❌ Conflict: Target file already exists at {new_abs}"
        raise FileExistsError(error_msg)

    safe_old = make_safe_path(old_abs)
    safe_new = make_safe_path(new_abs)

    try:
        shutil.move(safe_old, safe_new) 
    except Exception as e:
        raise RuntimeError(ui.print_error(f" ❌ Error: Impossible to move the file \n Old path {safe_old} \n New path {safe_new}", e))

def remove_empty_folders(target_path):
    if not os.path.exists(target_path):
        ui.print_log(f"The path '{target_path}' does not exist.")
        return

    target_dir = Path(target_path).resolve()

    for dirpath, dirnames, filenames in os.walk(target_dir, topdown=False):
        current_dir = Path(dirpath).resolve()
        if current_dir == target_dir:
            continue
            
        try:
            if not os.listdir(dirpath):
                try:
                    os.rmdir(dirpath)
                except OSError as e:
                    ui.print_log(f"⚠️ Warning: Could not delete empty folder '{dirpath}': {e}")
        except OSError as e:
            ui.print_log(f"⚠️ Warning: Could not inspect folder '{dirpath}': {e}")

def build_destination_lookup(clean_data_table=None) -> Dict[str, Tuple[str, str]]:
    """Maps destination stem back to (original_name, media_type)."""
    lookup = {}
    if clean_data_table is not None and not clean_data_table.empty:
        for _, row in clean_data_table.iterrows():
            corr = str(row.get('Corrected', ''))
            orig = str(row.get('File', row.get('Original', '')))
            media = str(row.get('Media', ''))
            lookup[corr] = (orig, media)
    return lookup

def infer_media_type_from_destination(p_new: Path, movies_dir: Optional[Path] = None, tv_dir: Optional[Path] = None) -> str:
    """Infers media type based on destination directory relative location."""
    try:
        if movies_dir and p_new.resolve().is_relative_to(movies_dir.resolve()):
            return "movie"
        if tv_dir and p_new.resolve().is_relative_to(tv_dir.resolve()):
            return "tv"
    except Exception:
        pass
    return "unknown"

def execute_single_file_move(old, new, lookup: dict, movies_dir: Optional[Path] = None, tv_dir: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
    """Moves an individual media file and dispatches success/error email notifications."""
    p_old = Path(old)
    p_new = Path(new)
    try:
        move_file(old, new)

        orig_name, media_type = lookup.get(p_new.stem, (p_old.name, "unknown"))
        if media_type == "unknown":
            media_type = infer_media_type_from_destination(p_new, movies_dir, tv_dir)

        mail.send_media_success_email(
            media_name=p_new.name,
            original_name=orig_name,
            media_type=media_type,
            destination_path=str(p_new)
        )
        return True, None
    except (FileExistsError, RuntimeError) as e:
        ui.print_log(f" ⚠️ Skipping {p_old.name}: {e} \n")
        try:
            mail.send_error_email(
                error_message=str(e),
                affected_file=p_old.name
            )
        except Exception as mail_err:
            ui.print_log(f"⚠️ Warning: Failed to send error email: {mail_err}")
        return False, p_old.name

def move_media_files(paths, clean_data_table=None, source_path=None):
    success_count = 0
    failed_moves = []

    movies_dir = Path(MOVIES_FOLDER) if MOVIES_FOLDER else None
    tv_dir = Path(TV_SHOWS_FOLDER) if TV_SHOWS_FOLDER else None
    lookup = build_destination_lookup(clean_data_table)

    for old, new in paths:
        success, failed_file = execute_single_file_move(old, new, lookup, movies_dir, tv_dir)
        if success:
            success_count += 1
        else:
            failed_moves.append(failed_file)

    if success_count > 0:
        ui.print_log(f"\n✅ {success_count} files moved successfully!")

    if failed_moves:
        ui.print_log(f"❌ {len(failed_moves)} files could not be moved")

    cleanup_target = Path(source_path) if source_path else (Path(NOT_SORTED_MEDIA_FILES_FOLDER) if NOT_SORTED_MEDIA_FILES_FOLDER else None)
    if cleanup_target:
        remove_empty_folders(cleanup_target)

def get_file_quality_resolution(file_path):
    metadata = get_metadata_with_ffprobe(file_path)
    
    if not metadata:
        return None, None

    technical_blob = ""
    width_map = {
        3840: "2160p 4k",
        2560: "1440p",
        1920: "1080p",
        1280: "720p",
        720:  "480p"
    }

    # scan data from ffprobe
    streams = metadata.get('streams', [])
    for stream in streams:
        width = stream.get('width')
        if width:
            res_name = width_map.get(width, "")
            technical_blob += f" {width}x{stream.get('height')} {res_name} "
        
        technical_blob += f" {stream.get('codec_name')} {stream.get('pix_fmt')} {stream.get('color_space')} "

    fmt = metadata.get('format', {})
    technical_blob += f" {fmt.get('format_name')} "
    
    tags = fmt.get('tags', {})
    for key, value in tags.items():
        technical_blob += f" {value} "
    
    scan_string = technical_blob.replace('_', ' ').replace('.', ' ')

    # resolution
    final_res = None
    for pattern in RESOLUTION_PATTERNS:
        match = re.search(pattern, scan_string, flags=re.IGNORECASE)
        if match:
            final_res = match.group(0).strip()
            break

    # quality
    final_qual = None
    for pattern in QUALITY_PATTERNS:
        match = re.search(pattern, scan_string, flags=re.IGNORECASE)
        if match:
            final_qual = match.group(0).strip()
            break

    # fallback : bitrate
    if final_qual is None:
        raw_bitrate = fmt.get('bit_rate')
        if raw_bitrate:
            mbps = round(int(raw_bitrate) / 1000000)
            final_qual = f"{mbps}Mbps"

    return final_res, final_qual

def get_metadata_with_ffprobe(file_path):
    # Check if ffprobe is installed on the system
    if not shutil.which("ffprobe"):
        ui.print_log(
            "⚠️ Warning: ffprobe is not installed or not found in System PATH.\n"
            "FFmpeg is only required if you activate the resolution and quality tags feature.\n"
            "To install FFmpeg, see: docs/documentation.md#ffmpeg-setup\n"
            "Or disable it via: python main.py config --set options.resolution false\n"
        )
        return None

    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "stream=width,height,codec_name,pix_fmt,color_space",
        "-show_entries", "format=format_name,bit_rate,tags",
        "-of", "json", 
        file_path
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        ui.print_error("❌ Error: An error occured while running ffprobe",e)
        return None
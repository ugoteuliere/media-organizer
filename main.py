import sys
import time
import signal
import threading
from datetime import datetime
import traceback
from pathlib import Path
from src import ui, files, utils, mail


def process_media(args, autonomous=False, cycle=1):
    """Executes a single media discovery, rename, and sort cycle."""
    search_result = files.search_media_files(args.path, exit_if_empty=not autonomous)
    if search_result is None:
        if autonomous:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    messy_data_table, clean_data_table = search_result

    if messy_data_table.empty and clean_data_table.empty:
        if not autonomous:
            ui.print_log("❌ No media files found to process\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    # Match metadata via TMDB and AI fallback to resolve official filenames for messy files
    if not messy_data_table.empty:
        clean_data_table = utils.get_corrected_media_filenames(messy_data_table, clean_data_table)

    if clean_data_table.empty:
        if not autonomous:
            ui.print_log("❌ No media files to rename\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    has_renames = utils.has_files_to_rename(clean_data_table)

    if args.only_rename and not has_renames:
        if not autonomous:
            ui.print_log("❌ No media files to rename\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    if has_renames:
        ui.display_corrected_filenames(clean_data_table)

    # Simulation Mode: Preview renames and target paths without touching disk
    if getattr(args, "simulate", False) or ui.SIMULATE_ENABLED:
        if not args.only_rename:
            paths = files.sort_media_files(clean_data_table)
            ui.display_sorted_files(paths)
        ui.rich_print_log("\n[bold yellow]🔍 Simulation mode complete: No files were renamed or moved on disk.[/bold yellow]\n")
        return 0

    if has_renames:
        # User confirmation and physical rename on disk
        if not autonomous:
            ui.user_confirmation("rename the files")
        clean_data_table = files.rename_media_files(clean_data_table)

    if args.only_rename:
        for _, row in clean_data_table.iterrows():
            p = Path(str(row['Path']))
            mail.send_media_success_email(
                media_name=p.name,
                original_name=str(row.get('File', row.get('Original', p.name))),
                media_type=str(row.get('Media', 'unknown')),
                destination_path=str(p)
            )
        if autonomous:
            ui.print_log(f"Check {cycle} : Successfully renamed {len(clean_data_table)} file(s).")
        return 0

    # Sort and move files
    if not clean_data_table.empty:
        paths = files.sort_media_files(clean_data_table)
        ui.display_sorted_files(paths)
        if not autonomous:
            ui.user_confirmation("move the files to the correct folder")
        files.move_media_files(paths, clean_data_table, source_path=args.path)
        if autonomous:
            ui.print_log(f"Check {cycle} : Successfully processed {len(clean_data_table)} file(s).")
    else:
        ui.print_log("❌ No media files to sort and move\n")

    return 0


def run_daemon_loop(args, max_cycles=None, stop_event=None):
    """Runs continuous background polling watcher loop."""
    interval_min = ui.POLLING_INTERVAL
    interval_sec = interval_min * 60

    if stop_event is None:
        stop_event = threading.Event()

    def _sig_handler(signum, frame):
        stop_event.set()

    prev_int = None
    prev_term = None
    try:
        prev_int = signal.signal(signal.SIGINT, _sig_handler)
    except (ValueError, AttributeError):
        pass
    try:
        if hasattr(signal, "SIGTERM"):
            prev_term = signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass

    ui.print_log(f"Daemon mode started. Polling every {interval_min} minute(s). (Press Ctrl+C to stop)")

    cycles = 0
    try:
        while not stop_event.is_set():
            cycles += 1
            try:
                process_media(args, autonomous=True, cycle=cycles)
            except Exception as e:
                full_tb = traceback.format_exc()
                err_msg = f"Check {cycles} : Error: {e} \n\n ⤷ Error logs: {full_tb}"
                ui.print_log(err_msg)
                mail.send_error_email(error_message=err_msg, exception=e)

            if max_cycles is not None and cycles >= max_cycles:
                break

            start_sleep = time.time()
            while not stop_event.is_set() and (time.time() - start_sleep) < interval_sec:
                time_remaining = interval_sec - (time.time() - start_sleep)
                stop_event.wait(timeout=min(1.0, max(0.1, time_remaining)))

    except KeyboardInterrupt:
        stop_event.set()
    finally:
        if prev_int is not None:
            try:
                signal.signal(signal.SIGINT, prev_int)
            except Exception:
                pass
        if prev_term is not None and hasattr(signal, "SIGTERM"):
            try:
                signal.signal(signal.SIGTERM, prev_term)
            except Exception:
                pass

    ui.print_log("Daemon mode stopped.")
    return 0

_ORIG_LOOP = run_daemon_loop
run_autonomous_loop = run_daemon_loop


def main():
    try:
        # Parse command line arguments and options
        args = ui.parse_arguments()
        
        # Check if launched by double-clicking in Windows Explorer with no CLI arguments
        if ui.is_double_clicked():
            ui.hide_console_window()
            from src.config import config
            config.run_gui()
            return 0

        # Dispatch standalone GUI launcher or CLI config commands
        if getattr(args, "gui", False) is True:
            ui.hide_console_window()
            from src.config import config
            config.run_gui()
            return 0

        if getattr(args, "subcommand", None) in ("config", "configure"):
            ui.handle_config_command(args)
            return 0
        
        utils.verify_folders(
            only_rename=args.only_rename,
            custom_path=args.path,
            daemon=ui.DAEMON_ENABLED
        )

        if ui.DAEMON_ENABLED:
            if run_daemon_loop is not _ORIG_LOOP:
                return run_daemon_loop(args)
            if run_autonomous_loop is not _ORIG_LOOP:
                return run_autonomous_loop(args)
            return run_daemon_loop(args)

        return process_media(args, autonomous=False)
    
    except RuntimeError as error_message:
        ui.print_log(error_message)
        mail.send_error_email(error_message=str(error_message))
        sys.exit(1)

    except Exception as e:
        full_traceback = traceback.format_exc() 
        error_message = f" ❌ Error: A critical, unexpected error occurred  \n\n ⤷ Exception: {e} \n\n ⤷ Error logs: {full_traceback} \n"
        ui.print_log(error_message)
        mail.send_error_email(error_message=error_message, exception=e)
        sys.exit(1)
        

if __name__ == "__main__":
    main()
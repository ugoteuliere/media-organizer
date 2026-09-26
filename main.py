"""
Entry point for media-organizer.

Orchestrates the full media discovery, rename, and sort pipeline.

Key improvements:
- **B9**: The ``_global_excepthook`` email call is wrapped in
  ``except BaseException: pass`` so a mail failure does not obscure the
  original exception.
- **B12**: Catches :exc:`~src.exceptions.MediaOrganizerError` (and subtypes)
  at the boundary instead of relying on ``sys.exit()`` deep in library code.
- **P7 / R7**: Daemon sleep uses ``stop_event.wait(timeout=interval_sec)``
  instead of a 1-second busy-loop.
- Uses ``runtime.xxx`` flags from :mod:`src.runtime_config` throughout.
"""

from __future__ import annotations

import signal
import sys
import threading
import traceback
from pathlib import Path

from src import files, mail, ui, utils
from src.exceptions import MediaOrganizerError
from src.runtime_config import runtime


def _global_excepthook(exc_type, exc_value, exc_traceback):
    """Intercepts unhandled exceptions and dispatches an error email before terminating.

    B9 fix: email dispatch is wrapped in ``except BaseException`` so a mail
    failure (e.g. SMTP not configured) cannot suppress the original traceback.
    """
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    err_msg = f" Critical unhandled crash:\n\n{tb_str}"

    try:
        mail.send_error_email(error_message=err_msg, exception=exc_value)
    except BaseException:  # noqa: BLE001 – intentionally broad: never hide the real exception
        pass

    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _global_excepthook


def process_media(args, daemon: bool = False, cycle: int = 1) -> int:
    """Executes a single media discovery, rename, and sort cycle."""
    search_result = files.search_media_files(args.path, exit_if_empty=not daemon)
    if search_result is None:
        if daemon:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    messy_data_table, clean_data_table = search_result

    if messy_data_table.empty and clean_data_table.empty:
        if not daemon:
            ui.print_log("No media files found to process\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    # Match metadata via TMDB and AI fallback to resolve official filenames
    if not messy_data_table.empty:
        clean_data_table = utils.get_corrected_media_filenames(messy_data_table, clean_data_table)

    if clean_data_table.empty:
        if not daemon:
            ui.print_log("No media files to rename\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    has_renames = utils.has_files_to_rename(clean_data_table)

    if args.only_rename and not has_renames:
        if not daemon:
            ui.print_log("No media files to rename\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")
        return 0

    if has_renames and not daemon:
        ui.display_corrected_filenames(clean_data_table)

    # Simulation mode: preview renames and target paths without touching disk
    if runtime.simulate_enabled or getattr(args, "simulate", False):
        if not args.only_rename:
            paths = files.sort_media_files(clean_data_table)
            ui.display_sorted_files(paths)
        ui.rich_print_log("\n[bold yellow]Simulation mode complete: No files were renamed or moved on disk.[/bold yellow]\n")
        return 0

    if has_renames:
        if not daemon:
            ui.user_confirmation("rename the files")
        clean_data_table = files.rename_media_files(clean_data_table)

    if args.only_rename:
        for _, row in clean_data_table.iterrows():
            p = Path(str(row["Path"]))
            orig_name = str(row.get("File", row.get("Original", p.name)))
            if daemon:
                ui.log_success(orig_name, p.name, f"{p} (in-place)")
            mail.send_media_success_email(
                media_name=p.name,
                original_name=orig_name,
                media_type=str(row.get("Media", "unknown")),
                destination_path=str(p),
            )
        if daemon:
            ui.print_log(f"Check {cycle} : Successfully renamed {len(clean_data_table)} file(s).")
        return 0

    # Sort and move files
    if not clean_data_table.empty:
        paths = files.sort_media_files(clean_data_table)
        if not paths:
            if not daemon:
                ui.print_log("No media files to sort and move\n")
            else:
                ui.log_info(f"Check {cycle} : No media to process")
            return 0
        if not daemon:
            ui.display_sorted_files(paths)
            ui.user_confirmation("move the files to the correct folder")
        success_count, fail_count = files.move_media_files(paths, clean_data_table, source_path=args.path)
        if daemon:
            total = success_count + fail_count
            if fail_count > 0:
                ui.log_info(f"Check {cycle} : {success_count}/{total} files processed ({fail_count} failed)")
            else:
                ui.print_log(f"Check {cycle} : Successfully processed {success_count}/{total} file(s).")
    else:
        if not daemon:
            ui.print_log("No media files to sort and move\n")
        else:
            ui.print_log(f"Check {cycle} : No media to process")

    return 0


def run_daemon_loop(
    args,
    max_cycles: int | None = None,
    stop_event: threading.Event | None = None,
    verify_on_cycle: bool = False,
) -> int:
    """Runs continuous background polling watcher loop.

    P7 / R7 fix: Uses ``stop_event.wait(timeout=interval_sec)`` for the inter-
    cycle sleep instead of a 1-second busy-poll loop.  This is both more CPU-
    efficient and more immediately responsive to a stop signal.
    """
    interval_min = runtime.polling_interval
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
            if verify_on_cycle:
                try:
                    folder_status = utils.verify_folders(
                        only_rename=args.only_rename,
                        custom_path=args.path,
                        daemon=True,
                        simulate=runtime.simulate_enabled,
                        exit_on_error=False,
                    )
                except MediaOrganizerError:
                    folder_status = 1

                if folder_status != 0:
                    ui.log_error(
                        f"Check {cycles}: Media folders verification failed. Retrying in {interval_min} minute(s)..."
                    )
                else:
                    verify_on_cycle = False
                    try:
                        process_media(args, daemon=True, cycle=cycles)
                    except Exception as e:
                        full_tb = traceback.format_exc()
                        ui.log_error(f"Check {cycles}: Error: {e}")
                        try:
                            mail.send_error_email(
                                error_message=f"Check {cycles}: Error: {e}\n\n{full_tb}", exception=e
                            )
                        except BaseException:  # noqa: BLE001
                            pass
            else:
                try:
                    process_media(args, daemon=True, cycle=cycles)
                except Exception as e:
                    full_tb = traceback.format_exc()
                    ui.log_error(f"Check {cycles}: Error: {e}")
                    try:
                        mail.send_error_email(
                            error_message=f"Check {cycles}: Error: {e}\n\n{full_tb}", exception=e
                        )
                    except BaseException:  # noqa: BLE001
                        pass

            if max_cycles is not None and cycles >= max_cycles:
                break

            # P7/R7 fix: efficient single wait instead of 1-second busy-loop
            if not stop_event.is_set():
                stop_event.wait(timeout=interval_sec)

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


def main() -> int:
    """Main entry point — parses arguments and dispatches to the correct handler."""
    try:
        args = ui.parse_arguments()

        # Double-click launch: open GUI
        if ui.is_double_clicked():
            ui.hide_console_window()
            from src.config import config

            config.run_gui()
            return 0

        if getattr(args, "gui", False) is True:
            ui.hide_console_window()
            from src.config import config

            config.run_gui()
            return 0

        if getattr(args, "subcommand", None) in ("config", "configure"):
            ui.handle_config_command(args)
            return 0

        if runtime.daemon_enabled:
            try:
                folder_ok = (
                    utils.verify_folders(
                        only_rename=args.only_rename,
                        custom_path=args.path,
                        daemon=True,
                        simulate=runtime.simulate_enabled,
                        exit_on_error=False,
                    )
                    == 0
                )
            except MediaOrganizerError:
                folder_ok = False

            if not folder_ok:
                ui.log_error(
                    f"Initial media folders verification failed. Daemon will retry every {runtime.polling_interval} minute(s)..."
                )
            return run_daemon_loop(args, verify_on_cycle=(not folder_ok))

        utils.verify_folders(
            only_rename=args.only_rename,
            custom_path=args.path,
            daemon=False,
            simulate=runtime.simulate_enabled,
        )

        return process_media(args, daemon=False)

    except (MediaOrganizerError, RuntimeError) as e:
        # B12: typed exceptions bubble up from library functions
        ui.print_log(str(e))
        try:
            mail.send_error_email(error_message=str(e))
        except BaseException:  # noqa: BLE001
            pass
        sys.exit(1)

    except Exception as e:
        full_traceback = traceback.format_exc()
        error_message = (
            f" Error: A critical, unexpected error occurred\n\n"
            f" Exception: {e}\n\n"
            f" Error logs: {full_traceback}\n"
        )
        ui.print_log(error_message)
        try:
            mail.send_error_email(error_message=error_message, exception=e)
        except BaseException:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
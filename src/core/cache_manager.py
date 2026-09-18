"""Cache management utilities for clearing accumulated work directory files."""

import shutil
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..config import WORK_DIR


def calculate_cache_size() -> tuple[int, dict[str, int]]:
    """Calculate total cache size and breakdown by subdirectory.

    Returns:
        Tuple of (total_bytes, breakdown_dict) where breakdown_dict maps
        subdirectory name to size in bytes.
    """
    if not WORK_DIR.exists():
        return (0, {})

    # Known cache subdirectories
    subdirs = ["download", "interleave", "anki", "punctuation_cache"]
    breakdown = {}

    for subdir_name in subdirs:
        subdir = WORK_DIR / subdir_name
        if not subdir.exists():
            breakdown[subdir_name] = 0
            continue

        subdir_size = 0
        try:
            # Walk all files in subdirectory
            for file_path in subdir.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    try:
                        subdir_size += file_path.stat().st_size
                    except (OSError, PermissionError):
                        # Skip files we can't access
                        continue
        except (OSError, PermissionError):
            # Skip subdirectories we can't access
            pass

        breakdown[subdir_name] = subdir_size

    # Calculate total from breakdown to ensure consistency
    total_bytes = sum(breakdown.values())

    return (total_bytes, breakdown)


def format_size(bytes_count: int) -> str:
    """Convert bytes to human-readable format.

    Args:
        bytes_count: Size in bytes

    Returns:
        Formatted string like "1.5 GB" or "234.2 MB"
    """
    if bytes_count == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_count)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    # Show 1 decimal place for MB and above
    if unit_index >= 2:
        return f"{size:.1f} {units[unit_index]}"
    else:
        return f"{int(size)} {units[unit_index]}"


def clear_cache_directory(progress_callback=None) -> tuple[bool, str, dict]:
    """Delete all cache subdirectories.

    Args:
        progress_callback: Optional callable(current, total, message) for progress updates

    Returns:
        Tuple of (success, message, stats_dict) where stats_dict contains:
        - freed_bytes: Total bytes freed
        - failed_dirs: List of directories that couldn't be deleted
    """
    subdirs = ["download", "interleave", "anki", "punctuation_cache"]
    total_subdirs = len(subdirs)
    freed_bytes = 0
    failed_dirs = []

    for idx, subdir_name in enumerate(subdirs):
        subdir = WORK_DIR / subdir_name

        if progress_callback:
            progress_callback(idx + 1, total_subdirs, f"Clearing {subdir_name}...")

        if not subdir.exists():
            continue

        # Calculate size before deletion
        try:
            subdir_size = 0
            for file_path in subdir.rglob("*"):
                if file_path.is_file():
                    try:
                        subdir_size += file_path.stat().st_size
                    except (OSError, PermissionError):
                        pass

            # Delete the subdirectory
            shutil.rmtree(subdir)

            # Recreate empty directory
            subdir.mkdir(parents=True, exist_ok=True)

            freed_bytes += subdir_size

        except PermissionError:
            failed_dirs.append(f"{subdir_name} (permission denied)")
        except OSError as e:
            failed_dirs.append(f"{subdir_name} ({str(e)})")

    # Build result message
    stats = {
        "freed_bytes": freed_bytes,
        "failed_dirs": failed_dirs
    }

    if failed_dirs:
        message = f"Partially cleared cache\nFreed {format_size(freed_bytes)}\n\nFailed to clear:\n"
        message += "\n".join(f"  • {d}" for d in failed_dirs)
        return (False, message, stats)
    else:
        message = f"Successfully cleared cache\nFreed {format_size(freed_bytes)}"
        return (True, message, stats)


def auto_clear_if_needed(threshold_bytes: int, logger=None) -> bool:
    """Clear cache if total size exceeds threshold.

    Args:
        threshold_bytes: Size threshold in bytes; cache is cleared if exceeded.
        logger: Optional RunLogger for structured logging.

    Returns:
        True if cache was cleared, False otherwise.
    """
    total_bytes, _ = calculate_cache_size()
    if total_bytes < threshold_bytes:
        return False

    if logger:
        logger.info(
            "Auto-clearing cache",
            cache_size=total_bytes,
            threshold=threshold_bytes,
            cache_size_human=format_size(total_bytes),
            threshold_human=format_size(threshold_bytes),
        )

    success, message, stats = clear_cache_directory()

    if logger:
        logger.info(
            "Auto-clear complete",
            success=success,
            freed_bytes=stats.get("freed_bytes", 0),
            freed_human=format_size(stats.get("freed_bytes", 0)),
            failed_dirs=stats.get("failed_dirs", []),
        )

    return True


class CacheWorker(QThread):
    """Background worker for cache operations."""

    size_calculated = Signal(object, dict)  # (total_bytes, breakdown_dict) - use object to handle large ints
    progress = Signal(int, int, str)        # (current, total, message)
    finished = Signal(str, dict)            # (summary_message, stats_dict)
    error = Signal(str)                     # Error message

    def __init__(self, mode="calculate"):
        """Initialize cache worker.

        Args:
            mode: "calculate" to compute size, "clear" to delete cache
        """
        super().__init__()
        self.mode = mode

    def run(self):
        """Execute cache operation."""
        try:
            if self.mode == "calculate":
                self._calculate_size()
            elif self.mode == "clear":
                self._clear_cache()
        except Exception as e:
            self.error.emit(f"Cache operation failed: {e}")

    def _calculate_size(self):
        """Calculate cache size and emit result."""
        total_bytes, breakdown = calculate_cache_size()
        self.size_calculated.emit(total_bytes, breakdown)

    def _clear_cache(self):
        """Clear cache and emit result."""
        def progress_callback(current, total, message):
            self.progress.emit(current, total, message)

        success, message, stats = clear_cache_directory(progress_callback)
        self.finished.emit(message, stats)

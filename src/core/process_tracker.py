"""Centralized subprocess tracker for cancellation support.

Wraps subprocess.Popen so that a running child process can be killed
immediately from another thread (e.g. when the user clicks Cancel).
"""

import subprocess
import threading
import time


class CancelledError(Exception):
    """Raised when an operation is killed due to user cancellation."""
    pass


def interruptible_sleep(seconds, cancelled_check):
    """Sleep for *seconds*, checking cancelled_check every 0.5s.

    Raises CancelledError if cancelled_check() returns True.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cancelled_check and cancelled_check():
            raise CancelledError("Operation cancelled")
        remaining = end - time.monotonic()
        time.sleep(min(0.5, max(0, remaining)))


class ProcessTracker:
    """Thread-safe tracker that can kill the active subprocess on demand.

    Usage:
        tracker = ProcessTracker()
        # On the worker thread:
        result = tracker.run(["ffmpeg", ...], capture_output=True, text=True)
        # On the UI thread:
        tracker.cancel()  # kills ffmpeg immediately
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active: subprocess.Popen | None = None
        self._cancelled = False

    def run(self, cmd, **kwargs):
        """Drop-in replacement for subprocess.run() that tracks the process.

        Raises CancelledError if cancelled before or during execution.
        """
        if self._cancelled:
            raise CancelledError("Operation cancelled")

        # Convert capture_output to explicit pipes for Popen
        if kwargs.pop("capture_output", False):
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE

        check = kwargs.pop("check", False)
        timeout = kwargs.pop("timeout", None)

        proc = subprocess.Popen(cmd, **kwargs)
        with self._lock:
            if self._cancelled:
                proc.kill()
                proc.wait()
                raise CancelledError("Operation cancelled")
            self._active = proc

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        except Exception:
            proc.kill()
            proc.wait()
            raise
        finally:
            with self._lock:
                self._active = None

        if self._cancelled:
            raise CancelledError("Operation cancelled")

        result = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=stdout, stderr=stderr,
            )

        return result

    def cancel(self):
        """Kill the active subprocess immediately. Thread-safe."""
        with self._lock:
            self._cancelled = True
            if self._active is not None:
                try:
                    self._active.kill()
                except OSError:
                    pass  # already dead

    def reset(self):
        """Reset cancelled state for reuse."""
        with self._lock:
            self._cancelled = False
            self._active = None

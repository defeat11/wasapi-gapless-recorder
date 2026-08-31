import threading
from typing import Dict, Optional

class SharedState:
    """
    A thread-safe class for tracking and sharing the recording state, 
    including elapsed time, current segment, segment progress, and segment statuses.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._statuses: Dict[int, str] = {}
        self._elapsed_seconds: float = 0.0
        self._segment_progress: float = 0.0
        self._current_segment: int = 1
        self._latest_key_points: str = ""
        self._segment_seconds: int = 300

    @property
    def elapsed_seconds(self) -> float:
        with self._lock:
            return self._elapsed_seconds

    @elapsed_seconds.setter
    def elapsed_seconds(self, value: float):
        with self._lock:
            self._elapsed_seconds = value

    @property
    def segment_progress(self) -> float:
        with self._lock:
            return self._segment_progress

    @segment_progress.setter
    def segment_progress(self, value: float):
        with self._lock:
            self._segment_progress = value

    @property
    def current_segment(self) -> int:
        with self._lock:
            return self._current_segment

    @current_segment.setter
    def current_segment(self, value: int):
        with self._lock:
            self._current_segment = value

    @property
    def latest_key_points(self) -> str:
        with self._lock:
            return self._latest_key_points

    @latest_key_points.setter
    def latest_key_points(self, value: str):
        with self._lock:
            return self._latest_key_points

    @property
    def segment_seconds(self) -> int:
        with self._lock:
            return self._segment_seconds

    @segment_seconds.setter
    def segment_seconds(self, value: int):
        with self._lock:
            return self._segment_seconds

    # --- Thread-Safe Status Methods ---
    def set_status(self, segment: int, status: str):
        """Sets the status of a specific segment (e.g., 'recording', 'queued', 'processing', 'done', 'error')."""
        with self._lock:
            self._statuses[segment] = status

    def get_status(self, segment: int) -> Optional[str]:
        """Gets the status of a specific segment."""
        with self._lock:
            return self._statuses.get(segment)

    @property
    def statuses(self) -> Dict[int, str]:
        """Returns a copy of all segment statuses."""
        with self._lock:
            return dict(self._statuses)

    # --- Method-Based Getters and Setters (for flexibility/compatibility) ---
    def get_elapsed_seconds(self) -> float:
        return self.elapsed_seconds

    def set_elapsed_seconds(self, value: float):
        self.elapsed_seconds = value

    def get_segment_progress(self) -> float:
        return self.segment_progress

    def set_segment_progress(self, value: float):
        self.segment_progress = value

    def get_current_segment(self) -> int:
        return self.current_segment

    def set_current_segment(self, value: int):
        self.current_segment = value

    def get_latest_key_points(self) -> str:
        return self.latest_key_points

    def set_latest_key_points(self, value: str):
        self.latest_key_points = value

    def get_all_statuses(self) -> Dict[int, str]:
        return self.statuses

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock


@dataclass
class ActiveFault:
    mode: str = "none"
    latency_ms: int = 0
    error_status: int = 500
    expires_at: datetime | None = None


class FaultController:
    """In-memory fault injection for approved reliability experiments.

    State lives in the process on purpose. A restart clears the fault, which is
    the behaviour we want when Kubernetes replaces the pod.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._fault = ActiveFault()

    def current(self) -> ActiveFault:
        with self._lock:
            fault = self._fault
            if fault.expires_at is not None and datetime.now(timezone.utc) >= fault.expires_at:
                self._fault = ActiveFault()
                return self._fault
            return ActiveFault(
                mode=fault.mode,
                latency_ms=fault.latency_ms,
                error_status=fault.error_status,
                expires_at=fault.expires_at,
            )

    def apply(self, mode: str, latency_ms: int, error_status: int, duration_seconds: int) -> ActiveFault:
        with self._lock:
            expires = None
            if mode != "none" and duration_seconds > 0:
                expires = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            self._fault = ActiveFault(
                mode=mode,
                latency_ms=latency_ms,
                error_status=error_status,
                expires_at=expires,
            )
            # Don't call current() here. threading.Lock is not re-entrant, and
            # current() takes the same lock.
            fault = self._fault
            return ActiveFault(
                mode=fault.mode,
                latency_ms=fault.latency_ms,
                error_status=fault.error_status,
                expires_at=fault.expires_at,
            )

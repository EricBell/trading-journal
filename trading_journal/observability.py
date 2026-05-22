"""Upload performance logging — sends structured events to OpenObserve over HTTP.

Disabled by default. Enable via env vars (see docs/openobserve-upload-logging.md).
All public methods are no-ops when disabled; HTTP failures are non-fatal.
"""

import json
import logging
import os
import time
import uuid
from base64 import b64encode
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class UploadPerfLogger:
    """Sends structured upload-stage events to an OpenObserve stream.

    Use UploadPerfLogger.from_env() in application code.
    Use UploadPerfLogger.noop() when no logger is needed (e.g. CLI paths).
    """

    def __init__(
        self,
        enabled: bool,
        url: str,
        org: str,
        stream: str,
        username: str,
        password: str,
        timeout_s: float,
    ) -> None:
        self.enabled = enabled
        self._url = url.rstrip('/')
        self._org = org
        self._stream = stream
        self._auth = b64encode(f"{username}:{password}".encode()).decode()
        self._timeout = timeout_s
        self._stage_times: List[tuple] = []  # (name, elapsed_ms)

    @classmethod
    def from_env(cls) -> "UploadPerfLogger":
        enabled_val = os.environ.get('UPLOAD_PERF_LOGGING_ENABLED', 'false').lower()
        return cls(
            enabled=enabled_val in ('1', 'true', 'yes'),
            url=os.environ.get('OPENOBSERVE_URL', 'http://localhost:5080'),
            org=os.environ.get('OPENOBSERVE_ORG', 'default'),
            stream=os.environ.get('OPENOBSERVE_STREAM', 'trading_journal_uploads'),
            username=os.environ.get('OPENOBSERVE_USERNAME', ''),
            password=os.environ.get('OPENOBSERVE_PASSWORD', ''),
            timeout_s=float(os.environ.get('OPENOBSERVE_TIMEOUT_SECONDS', '1.0')),
        )

    @classmethod
    def noop(cls) -> "UploadPerfLogger":
        """Return a disabled logger for code paths that don't need instrumentation."""
        return cls(enabled=False, url='', org='', stream='', username='', password='', timeout_s=1.0)

    @staticmethod
    def new_session_id() -> str:
        return uuid.uuid4().hex[:12]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def event(self, event_name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Send a one-shot event (no timing)."""
        if not self.enabled:
            return
        payload = {
            'event': event_name,
            '_timestamp': _now_iso(),
            **(data or {}),
        }
        self._send(payload)

    @contextmanager
    def stage(self, stage_name: str, **fields: Any) -> Generator[Dict[str, Any], None, None]:
        """Context manager that times a pipeline stage and sends one event.

        Callers may write extra stats into the yielded dict; they are merged
        into the outgoing payload at the end of the block.

            with ul.stage("bulk_upsert_trades", upload_session_id=sid) as ctx:
                insert_count, update_count = do_upsert()
                ctx['records_inserted'] = insert_count
                ctx['records_updated'] = update_count
        """
        if not self.enabled:
            yield {}
            return

        ctx: Dict[str, Any] = {}
        exc: Optional[Exception] = None
        start = time.perf_counter()
        try:
            yield ctx
        except Exception as e:
            exc = e
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            self._stage_times.append((stage_name, elapsed_ms))
            payload = {
                'event': 'csv_upload_stage',
                'stage': stage_name,
                'status': 'error' if exc else 'success',
                'elapsed_ms': elapsed_ms,
                '_timestamp': _now_iso(),
                **fields,
                **ctx,
            }
            if exc:
                payload['error_type'] = type(exc).__name__
                payload['error_message'] = str(exc)
            self._send(payload)

    def summary(self) -> Dict[str, Any]:
        """Return aggregate stats across all completed stages (for the summary event)."""
        if not self._stage_times:
            return {}
        total_ms = sum(ms for _, ms in self._stage_times)
        slowest_name, slowest_ms = max(self._stage_times, key=lambda t: t[1])
        return {
            'total_elapsed_ms': total_ms,
            'slowest_stage': slowest_name,
            'slowest_stage_elapsed_ms': slowest_ms,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send(self, payload: Dict[str, Any]) -> None:
        try:
            endpoint = f"{self._url}/api/{self._org}/{self._stream}/_json"
            body = json.dumps([payload]).encode('utf-8')
            req = Request(
                endpoint,
                data=body,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Basic {self._auth}',
                },
                method='POST',
            )
            urlopen(req, timeout=self._timeout)
        except URLError as e:
            logger.debug("OpenObserve unreachable (non-fatal): %s", e)
        except Exception as e:
            logger.debug("OpenObserve send failed (non-fatal): %s", e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

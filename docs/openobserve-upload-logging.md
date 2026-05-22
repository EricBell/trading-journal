# Upload Performance Logging with OpenObserve

Instrumentation for diagnosing slow CSV uploads. Off by default — enable when you need
insight into which pipeline stage is consuming time.

---

## 1. Start OpenObserve

```bash
docker compose -f docker-compose.openobserve.yml up -d
```

Open the UI at http://localhost:5080  
Login: `admin@example.com` / `Complexpass#123`

---

## 2. Enable logging in the app

Set these env vars before starting the Trading Journal (or add them to your `.env`):

```bash
UPLOAD_PERF_LOGGING_ENABLED=true
OPENOBSERVE_URL=http://localhost:5080
OPENOBSERVE_ORG=default
OPENOBSERVE_STREAM=trading_journal_uploads
OPENOBSERVE_USERNAME=admin@example.com
OPENOBSERVE_PASSWORD=Complexpass#123
OPENOBSERVE_TIMEOUT_SECONDS=1.0   # default — keep short so a slow OO never stalls uploads
```

To disable again:

```bash
UPLOAD_PERF_LOGGING_ENABLED=false   # or just unset the var
```

---

## 3. Upload a CSV

Go to `/ingest` and upload normally. The upload still redirects to trades when complete.
Check OpenObserve immediately after.

---

## 4. Query in OpenObserve

Navigate to **Logs → trading_journal_uploads**.

### See all events for one upload session

```sql
upload_session_id = 'abc123def456'
```

The `upload_session_id` is a 12-character hex string printed in the app log at DEBUG level,
or visible in the first `upload_received` event.

### Compare stage timings

```sql
event = 'csv_upload_stage' | stats sum(elapsed_ms) by stage
```

### Find the slowest stage

```sql
event = 'upload_complete' | table upload_session_id, slowest_stage, slowest_stage_elapsed_ms, total_elapsed_ms
```

### See failures

```sql
status = 'error'
```

---

## 5. Event reference

### `upload_received`
Fired at the start of every upload (dry run and live).

| Field | Type | Description |
|---|---|---|
| `upload_session_id` | string | Correlates all events for this upload |
| `user_id` | int | |
| `file_count` | int | Number of files in the upload |
| `filenames` | list | File names (no path, no account numbers) |
| `file_size_bytes` | int | Total bytes across all files |
| `dry_run` | bool | Whether this is a preview-only run |

### `csv_upload_stage`
One event per instrumented pipeline stage.

| Field | Type | Description |
|---|---|---|
| `stage` | string | See stage list below |
| `status` | string | `success` or `error` |
| `elapsed_ms` | int | Wall-clock duration of the stage |
| `upload_session_id` | string | |
| `user_id` | int | |
| Stage-specific fields | varies | See below |

**Stages and their extra fields:**

| Stage | Extra fields |
|---|---|
| `csv_parse` | `file_count`, `records_emitted`, `fills` |
| `record_validation` | `records_valid`, `records_invalid` |
| `bulk_upsert_trades` | `records_in`, `records_inserted`, `records_updated` |
| `position_rebuild` | `affected_symbols` (list), `positions_rebuilt`, `options_expired` |
| `completed_trade_rebuild` | `completed_trades` |

### `upload_complete`
Summary event fired after a successful live upload.

| Field | Type | Description |
|---|---|---|
| `records_inserted` | int | |
| `records_updated` | int | |
| `completed_trades` | int | |
| `total_elapsed_ms` | int | Sum across all timed stages |
| `slowest_stage` | string | Stage name with highest elapsed_ms |
| `slowest_stage_elapsed_ms` | int | |

### `upload_failed`
Fired when an exception aborts the upload.

| Field | Type | Description |
|---|---|---|
| `error_type` | string | Exception class name |
| `error_message` | string | Exception message |

---

## 6. What to look for

The two stages most likely to dominate upload time:

- **`completed_trade_rebuild`** — full rebuild of all completed trades for the user.
  This is O(all-time fills) and will grow as trade history accumulates. If this is > 5s,
  it is the primary optimization target.

- **`position_rebuild`** — already symbol-scoped (not a full rebuild), so this scales
  with the number of symbols in the uploaded file, not total history. If this is slow,
  look at `affected_symbols` count and positions per symbol.

- **`bulk_upsert_trades`** — includes per-record account resolution and the UPSERT.
  If this is slow relative to record count, check network latency to the PostgreSQL server.

---

## 7. Security notes

- Account numbers are never logged (they are not included in any event payload).
- File paths are not logged; only filenames.
- The OpenObserve credentials in `docker-compose.openobserve.yml` are for local dev only.
  Change them for any shared or internet-accessible deployment.

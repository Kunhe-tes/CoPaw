# System Runtime Diagnostic Design

## 1. Goal

Provide a periodic, instance-scoped view of the current Swe backend service
runtime. Each Kubernetes Pod emits machine-readable logs that downstream
infrastructure asynchronously writes into MySQL.

The diagnostic answers:

- How many SSE connections are currently open, and what was the recent peak?
- Is the single Uvicorn worker's event loop responsive?
- What resources is the current Swe Python process using?
- How much capacity remains on the filesystem containing
  `/opt/deployments/app`?
- Which Pods are currently registered and have recently reported?

## 2. Scope

### Included

- Runtime Instance identity from the `HOSTNAME` environment variable.
- Runtime Instance registration, 75-minute lease renewal, and graceful
  deregistration.
- SSE current and peak concurrent connections.
- Event-loop lag sampled every second.
- Current Swe/Uvicorn Python process resource usage.
- Filesystem usage for `/opt/deployments/app`.
- INFO-level, single-line, machine-readable diagnostic logs.
- One Runtime Instance status table and one append-only diagnostic flow table.
- Thirty-day diagnostic-flow retention.

### Excluded

- Direct database writes from Swe.
- Kafka collection or consumer implementation.
- Flask workers, Supervisor process state, `app`, `dbus`, `xvfb`, or `xfce4`.
- WebSocket usage.
- Ordinary HTTP request throughput, latency, status codes, or error rates.
- Tenant, Workspace, Agent Run, Provider, LLM, MCP, or Cron statistics.
- MySQL and Redis health checks.
- Container cgroup limits or resources used by other processes.
- Recursive directory-size scans.
- A derived overall health status or unified load percentage.

## 3. Existing Runtime Constraints

- Swe runs FastAPI through Uvicorn with `workers=1`.
- The existing `/api/health/health` endpoint is a lightweight liveness probe
  and remains unchanged.
- Uvicorn does not currently expose a configured concurrency limit, so a
  meaningful worker-utilization percentage cannot be calculated.
- Swe already uses fixed-prefix, compact JSON logs for machine ingestion, such
  as `HOOK_TELEMETRY`.
- Kubernetes guarantees that active and historical Runtime Instances do not
  reuse the same `HOSTNAME`.

## 4. Considered Approaches

### 4.1 Direct database persistence

Swe periodically writes status and diagnostic rows directly to MySQL.

Rejected because it couples diagnostics to database availability and adds
database persistence responsibilities to every Pod.

### 4.2 Latest snapshot only

Each Pod upserts one diagnostic row keyed by `HOSTNAME`.

Rejected because it cannot support historical trend charts.

### 4.3 Structured logs with asynchronous downstream persistence

Swe emits lifecycle and diagnostic events as structured logs. Downstream
infrastructure consumes the logs and maintains the database tables.

Selected because it keeps the application-side collector independent from
Kafka and MySQL while preserving append-only history.

### 4.4 Diagnostic persistence shape

An EAV-style flow table with one row per metric was considered and rejected
because latest-state and historical-chart queries would require repeated
pivoting. A separate Diagnostic Run table was also rejected because the
consumer does not need run metadata beyond `hostname` and collection time.

The selected persistence shape has exactly two tables:

- One upserted Runtime Instance status table for presence and lease state.
- One append-only wide flow table with one row per Pod collection.

The wide table uses typed columns and does not contain JSON, LONGTEXT, or a
diagnostic run identifier.

## 5. Architecture

### 5.1 RuntimeDiagnosticManager

Add one process-local `RuntimeDiagnosticManager` owned by the FastAPI
application lifespan.

Responsibilities:

- Read and validate `HOSTNAME`.
- Emit Runtime Instance lifecycle events.
- Run the one-second sampler.
- Maintain the current 30-minute metric window.
- Read instantaneous process and storage metrics.
- Emit periodic `diagnostic_flow` events.

The manager must not initialize tenant Workspaces or call external services.

### 5.2 Lifecycle

1. After application startup completes, emit `instance_registered`.
2. Start the one-second event-loop and process CPU sampler.
3. Wait 120 seconds plus a random 0-10 second jitter.
4. Emit the first `diagnostic_flow`.
5. Emit subsequent `diagnostic_flow` events every 30 minutes.
6. On graceful shutdown, stop the sampler and emit
   `instance_deregistered`.

The first diagnostic window is shorter than 30 minutes because it begins at
startup and emits after the initial delay.

If `HOSTNAME` is absent, structured diagnostic events cannot be keyed. The
manager logs an ordinary error and does not emit Runtime Diagnostic events.

### 5.3 Window Rotation

After each `diagnostic_flow` event:

- Reset event-loop lag samples and the blocked count.
- Reset process CPU samples.
- Reset `sse_peak_connections` to the current active SSE count, not zero, so
  connections spanning multiple windows remain represented.
- Preserve `sse_active_connections`.

Window rotation and sampling must be synchronized so samples are not lost or
counted in both windows.

## 6. Metric Collection

### 6.1 SSE Connections

Count only responses whose content type is `text/event-stream`.

Use ASGI response-lifecycle instrumentation rather than route-name matching or
generic `StreamingResponse` detection:

- Increment the active count after the response start identifies an SSE
  response.
- Update the peak count after incrementing.
- Decrement exactly once when the response body finishes, the stream raises,
  or the client disconnects.

Metrics:

- `sse_active_connections`: active SSE connections at emission time.
- `sse_peak_connections`: maximum concurrent SSE connections in the current
  window.

WebSocket and non-SSE streaming responses are excluded.

### 6.2 Event-Loop Responsiveness

The background sampler runs every second and measures the difference between
the planned wake-up time and the actual wake-up time.

Metrics:

- `event_loop_lag_avg_ms`
- `event_loop_lag_p95_ms`
- `event_loop_lag_max_ms`
- `event_loop_blocked_count`

`event_loop_blocked_count` increments for samples above 1000ms. The P95
calculation must use a deterministic percentile implementation. If no valid
samples exist, the lag metrics are `null`.

### 6.3 Process Resources

Add `psutil` and inspect only the current Swe/Uvicorn Python process.

The one-second sampler collects process CPU usage for:

- `process_cpu_avg_percent`
- `process_cpu_max_percent`

Prime `psutil.Process.cpu_percent()` before accepting samples because its
first non-blocking call has no prior interval. Process CPU percentage may
exceed 100 on multi-core systems and must not be clamped.

Read the following instantaneous metrics when emitting `diagnostic_flow`:

- `process_rss_bytes`
- `process_vms_bytes`
- `process_thread_count`
- `process_open_fd_count`
- `process_uptime_seconds`

### 6.4 Storage

Use `psutil.disk_usage("/opt/deployments/app")`. This reports the filesystem
containing the path and does not recursively scan directory contents.

Metrics:

- `storage_total_bytes`
- `storage_used_bytes`
- `storage_free_bytes`
- `storage_used_percent`

### 6.5 Partial Failure

Each metric group is collected independently. If one metric cannot be
collected:

- Emit `null` for the failed fields.
- Emit all other successfully collected fields.
- Write the detailed exception to an ordinary error log.
- Do not emit an aggregate collection-error field.

## 7. Log Contract

All events use INFO-level compact single-line JSON. The fixed prefix is
followed by one space and the compact JSON payload:

```text
RUNTIME_DIAGNOSTIC {compact-json}
```

All payloads are flat objects. `event_at_ms` is the only event-time field and
contains Unix epoch milliseconds. Database consumers derive database
timestamps from it rather than from log-ingestion time.

### 7.1 Registration

```json
{"schema":"runtime_diagnostic.v1","event_type":"instance_registered","hostname":"swe-pod-abc","event_at_ms":1780992000000}
```

### 7.2 Deregistration

```json
{"schema":"runtime_diagnostic.v1","event_type":"instance_deregistered","hostname":"swe-pod-abc","event_at_ms":1780995600000}
```

### 7.3 Diagnostic Flow

```json
{"schema":"runtime_diagnostic.v1","event_type":"diagnostic_flow","hostname":"swe-pod-abc","event_at_ms":1780993800000,"sse_active_connections":3,"sse_peak_connections":12,"event_loop_lag_avg_ms":1.25,"event_loop_lag_p95_ms":3.8,"event_loop_lag_max_ms":1200.4,"event_loop_blocked_count":1,"process_cpu_avg_percent":18.5,"process_cpu_max_percent":82.1,"process_rss_bytes":536870912,"process_vms_bytes":1073741824,"process_thread_count":16,"process_open_fd_count":80,"process_uptime_seconds":7200,"storage_total_bytes":107374182400,"storage_used_bytes":53687091200,"storage_free_bytes":53687091200,"storage_used_percent":50.0}
```

Every metric field in `diagnostic_flow` is nullable.

## 8. Database Design

Swe does not create or write these tables at runtime. The DDL defines the
expected downstream persistence contract.

### 8.1 Runtime Instance Status

```sql
CREATE TABLE swe_runtime_instance_status (
    hostname VARCHAR(255) PRIMARY KEY,
    active BOOLEAN NOT NULL,
    registered_at DATETIME(3) NOT NULL,
    last_seen_at DATETIME(3) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    deregistered_at DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_active_expires_at (active, expires_at)
);
```

The table expresses Runtime Instance presence only. It does not contain
diagnostic metrics or a derived health status.

### 8.2 Diagnostic Flow

```sql
CREATE TABLE swe_runtime_diagnostic_flow (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    collected_at DATETIME(3) NOT NULL,

    sse_active_connections INT NULL,
    sse_peak_connections INT NULL,

    event_loop_lag_avg_ms DOUBLE NULL,
    event_loop_lag_p95_ms DOUBLE NULL,
    event_loop_lag_max_ms DOUBLE NULL,
    event_loop_blocked_count INT NULL,

    process_cpu_avg_percent DOUBLE NULL,
    process_cpu_max_percent DOUBLE NULL,
    process_rss_bytes BIGINT NULL,
    process_vms_bytes BIGINT NULL,
    process_thread_count INT NULL,
    process_open_fd_count INT NULL,
    process_uptime_seconds BIGINT NULL,

    storage_total_bytes BIGINT NULL,
    storage_used_bytes BIGINT NULL,
    storage_free_bytes BIGINT NULL,
    storage_used_percent DOUBLE NULL,

    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_hostname_collected_at (hostname, collected_at),
    INDEX idx_collected_at (collected_at)
);
```

No foreign key is defined from the flow table to the status table, so status
processing problems do not block append-only diagnostic history.

### 8.3 Downstream Write Rules

- `instance_registered`: upsert the status row, set `active=true`, derive
  timestamps from `event_at_ms`, and set `expires_at` to event time plus 75
  minutes.
- `diagnostic_flow`: append one flow row, set the existing status row to
  `active=true`, update `last_seen_at`, and renew `expires_at` to event time
  plus 75 minutes.
- `instance_deregistered`: set `active=false` and `deregistered_at` from
  `event_at_ms`.
- An instance is effective only when `active=true AND expires_at > NOW()`.
- Events for one `HOSTNAME` are expected to be consumed in order. The status
  table does not reject older event timestamps.
- Delete flow rows older than 30 days based on `collected_at`.
- Do not automatically delete status rows.

## 9. V1 Parameters

The first version uses the confirmed parameters below:

| Parameter | Value | Meaning |
|---|---:|---|
| First diagnostic delay | `120` seconds | Base startup delay |
| First diagnostic jitter | `10` seconds | Uniform random jitter from 0 to this value |
| Diagnostic interval | `1800` seconds | Periodic emission interval |
| Sampler interval | `1` second | Event-loop lag and process CPU sampling |
| Blocked lag threshold | `1000` milliseconds | Threshold for blocked count |
| Storage path | `/opt/deployments/app` | Filesystem usage target |

## 10. Error Handling and Shutdown

- Diagnostic collection must never fail application startup or terminate the
  application.
- Exceptions in the sampler or emitter are logged and the next interval
  continues.
- The periodic task must be cancelled and awaited during graceful shutdown.
- The deregistration event is best-effort. Abnormal termination is handled by
  the 75-minute lease expiry.
- Runtime Diagnostic logs must not contain secrets, tenant identifiers, paths
  other than the fixed storage target, or exception details.

## 11. Testing Strategy

### Unit Tests

- Event-loop lag average, deterministic P95, maximum, and blocked count.
- Window rotation resets lag and CPU samples.
- SSE increment, peak update, exact-once decrement, disconnect, and exception
  handling.
- SSE peak resets to current active count.
- Process CPU priming, average, maximum, and nullable failure behavior.
- Instantaneous process and storage metric mapping.
- Flat compact log payloads for all three event types.
- Individual metric failure produces `null` without suppressing the event.
- Missing `HOSTNAME` suppresses structured events and logs an error.

### Lifecycle Tests

- Registration is emitted after startup.
- First diagnostic runs after base delay plus bounded jitter.
- Periodic diagnostics continue after a collection failure.
- Graceful shutdown emits deregistration and stops the sampler.

### Contract Tests

- Every diagnostic log field maps to one flow-table column.
- Lifecycle events contain only the common contract fields.
- No excluded business-runtime or external-dependency fields appear.

## 12. Documentation Updates During Implementation

- Add Runtime Diagnostic logs to `analysis/playbook/log-entrypoints.md`.
- Add the diagnostic manager and metric scope to
  `analysis/observability-and-supporting-systems.md`.
- Document required Kubernetes `HOSTNAME` behavior and the downstream
  same-hostname event-ordering assumption.

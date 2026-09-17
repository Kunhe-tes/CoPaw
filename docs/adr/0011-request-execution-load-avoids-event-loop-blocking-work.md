# Request execution load avoids event-loop blocking work

Swe treats Request Execution Load as a responsiveness concern before a raw throughput concern. When work runs on a request path, streaming Agent turn, or Scheduled Run Boundary, data-size-dependent filesystem I/O, JSON encoding or decoding, model validation, compression, extraction, full-text search, and comparable synchronous processing should run outside the event-loop thread. This tightens earlier session-state guidance that allowed JSON serialization on the event loop: the trade-off is additional worker pressure, which should be handled by bounded worker boundaries, limiters, or executor isolation rather than by letting the event loop absorb variable-size work.

The cleanup order should first remove known event-loop blocking work from responsiveness-critical paths, then introduce worker isolation where offloaded heavy categories compete with smaller runtime-state work. Obvious heavyweight categories may receive local concurrency bounds during cleanup, but broad executor restructuring follows the blocking-work cleanup.

**Considered Options**

- Only move blocking filesystem calls off the event loop: rejected because JSON and validation can dominate latency for large session, chat, cron, or tool payloads.
- Increase default threadpool size for all offloaded work: rejected as the primary strategy because heavy archive, search, transcription, and provider-initialization tasks can starve smaller responsiveness-critical work.

**Consequences**

Repositories and runtime state stores should offload the full read/parse/validate and serialize/write operation when payload size can grow with user or tenant data. Heavy offloaded categories should gain bounded concurrency or separate execution resources before broad throughput tuning.

The first cleanup scope is responsiveness-critical state and tool work: chat metadata repositories, session JSON state, file read/edit tools, token usage persistence, and provider configuration writes. Archive, search, backup, and provider cold-start work are already outside the event loop often enough that their next concern is bounded worker isolation rather than first-pass event-loop cleanup.

Worker isolation should be organized by runtime impact rather than implementation technology. Runtime state work must not be starved by archive, search, backup, or provider-initialization work.

Provider local configuration reads and writes are runtime state work. Provider cold-start, connection tests, and model discovery are provider-initialization or external-provider work and should not share the responsiveness-critical runtime-state worker budget by default.

First-pass cleanup should use a small runtime-state worker helper rather than direct `asyncio.to_thread()` calls at each site. The helper may initially delegate to the default asyncio thread boundary, but it preserves the option to move runtime-state work to a dedicated executor or limiter without rewriting every repository and state-store call site.

The runtime-state worker helper belongs at the package runtime boundary, not in the FastAPI app entry point or a feature module. `src/swe/runtime_workers.py` is the intended dependency direction for app, agent tool, provider, and token-usage code that needs responsiveness-critical runtime-state offloading.

The first implementation of the helper should still use the default asyncio thread boundary. Dedicated executors or limiters are a second-stage change paired with diagnostics for worker pressure. Archive, search, backup, provider cold-start, and other heavyweight categories must not use the runtime-state helper merely because they are synchronous.

Chat metadata repositories should follow the cron job repository pattern during first-pass cleanup: offload the full file read, JSON parse, model validation, serialization, write, and atomic replacement boundary, and maintain a conservative file-signature snapshot plus chat-id index to avoid repeated full-file parsing when the underlying file has not changed.

Session JSON state should not gain a first-pass snapshot cache. Its first-pass cleanup should preserve the existing path-level coordination semantics while moving whole read/parse and serialize/write boundaries into runtime-state worker calls.

File read and edit tools should keep argument parsing, tenant path-boundary checks, tool error mapping, and response assembly on the async control path. File content reads and data-size-dependent text processing should move into runtime-state worker calls, while existing async atomic write behavior can remain the write boundary for first-pass cleanup.

Small router-local settings and text-asset file helpers may be cleaned up opportunistically, but they are not part of the first-pass completion boundary unless they become part of a responsiveness-critical path.

First-pass changes require both behavior tests and boundary tests. Boundary tests should prove that representative load, save, parse, serialize, or data-size-dependent text operations cross the runtime-state worker helper rather than executing directly on the async control path.

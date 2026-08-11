# SubAgent Run Monitor Uses Snapshot State And Direct Cancellation

The chat SubAgent Run Monitor will treat a backend SubAgent Run Snapshot as its authoritative state and use live stream events only to prompt refresh. User stop actions from the monitor call the runtime cancellation API directly for one Background SubAgent Run instead of sending a natural-language request for the Main Agent to call `cancel_subagent`, because cancellation should remain responsive even when the Main Agent stream is busy, disconnected, or already complete.

The monitor is scoped to the current conversation's Background SubAgent Runs and exposes only a slim user-facing snapshot. This deliberately avoids turning the chat widget into an agent-wide operations console or exposing full policies, raw logs, and complete AgentResult payloads in the default runtime UI.

This decision assumes the existing runtime-instance routing guarantees route monitor snapshot and stop requests to the runtime instance that owns the active Background SubAgent Run handle. Cross-instance cancellation, distributed supervisor state, and queue-backed worker ownership are outside this monitor decision.

The first monitor surface polls snapshots every 10 seconds while non-terminal runs exist, refreshes immediately when a live stream event hints that SubAgent state changed, and stops polling once all displayed runs are terminal. The monitor is not persisted into chat history; it is rebuilt from snapshots, disappears when there are no runs, keeps terminal runs until chat switch or a new Main Agent request, and treats its budget bar as elapsed time-budget consumption rather than task completion percentage. Snapshot summaries and error previews are backend-trimmed slim fields.

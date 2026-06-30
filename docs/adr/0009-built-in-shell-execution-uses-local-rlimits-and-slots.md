# Built-in Shell Execution uses local rlimits and slots

Built-in Shell Execution will enforce tenant shell resource protection with launch-time Unix rlimits, Unix process-group cleanup, and a per-backend-process Tenant Shell Execution Slot limiter. We intentionally do not introduce cgroups, Windows Job Objects, distributed coordination, or OS process counting in this decision because the immediate risk is tenant-launched shell work exhausting local host resources, and the existing `security.process_limits` policy can cover that path without changing the deployment model.

**Consequences:** CPU and memory ceilings are per process, not aggregate quotas for every process forked by a script. `shell_max_concurrent` limits concurrent `execute_shell_command` calls per tenant within one Swe backend process, not across a multi-instance cluster.

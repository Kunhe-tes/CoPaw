# Source Templates are explicitly provisioned

Swe treats each `default_<source_id>` Source Template as a privileged, ready-before-use platform asset rather than a side effect of a tenant request. Tenant bootstrap only consumes a strictly valid template; an authenticated internal/admin operation or CLI command creates or repairs it under a per-source file lock. This rejects the former lazy-copy approach because different first-access tenants could race on the same shared template and because a ready template can also be a live default-source runtime directory.

**Considered Options**

- Retain lazy creation and improve the `exists()` check: rejected because request-time writes still race across distinct tenant locks and make platform-template health depend on arbitrary tenant traffic.
- Force-copy `default/` over an existing template: rejected because it can overwrite a ready shared runtime asset.

**Consequences**

Deployments must pre-provision Source Templates before accepting first tenant traffic for a source. A missing or invalid template is an explicit retryable availability failure, not a silent fallback to `default/`.

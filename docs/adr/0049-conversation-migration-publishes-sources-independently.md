---
status: accepted
---

# Conversation migration publishes sources independently

On 2026-11-16 the user selected `(service_unit_id, tenant_id, source_id)` as the failure, retry and publication unit for new two-stage migrations. All Agents, workspaces and attributable shares of that source must pass together; a different source of the same tenant may publish independently. This refines ADR 0046 without changing existing tenant-level job identities or receipts.

Source publication uses separate SQL control rows and explicit source-aware runtime admission. Shared or ambiguous identity, share ownership and mutable input boundaries fail every affected source rather than guess ownership. Published sources must never be reread or overwritten by retries; shared infrastructure failures remain globally fatal. Old prepared jobs retain their original tenant boundary and cannot be silently converted in place.

---
status: accepted
---

# Explicit expert main execution keeps capability boundaries

A default-off Source administrator switch lets an explicitly selected Expert own ordinary Chat execution through a persisted, user-visible Chat binding. The Expert streams the response directly and replaces the Profile's role instruction, while preserving declared capabilities, private community dependencies, and the stricter per-message execution limits; it receives current-Chat context but neither Profile long-term memory nor further SubAgent delegation authority. This separates responsibility for the conversation from permission expansion, preserving specialist isolation while enabling continued direct interaction.

Existing SubAgent selection remains the disabled-switch behavior; the binding is released on Plan or Goal entry, and a disabled switch invalidates it on the next Chat entry or message submission without automatic restoration. In-flight messages keep their launch snapshot; later messages use the latest valid local expert configuration. The user confirmed the complete design on 2026-10-27; implementation and verification evidence are recorded separately in the delivery reports.

Expert main execution uses ordinary Chat's interactive approval and stop flow. Binding changes are saved immediately for subsequent messages, stale-page submissions are rejected with their draft preserved, and new or reset Chats return to Default Agent. An unavailable binding may execute again only when the same Expert identity becomes valid; deleted and recreated names do not transfer identity.

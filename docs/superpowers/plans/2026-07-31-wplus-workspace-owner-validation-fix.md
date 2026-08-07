---
title: W+ SOP workspace owner validation fix
type: fix
status: completed
date: 2026-07-31
origin: docs/adr/0013-wplus-sop-uses-persisted-session-and-structured-envelope.md
---

# W+ SOP workspace owner validation fix

## Problem

`OwnershipTuple.source_id` is the authenticated isolation source, while
`Chat.channel` is the transport channel. `_verified_owned_chat` previously
compared these unrelated values. A valid local request commonly has
`source_id=default` and `chat.channel=console`, so entry confirmation and retry
can fail with a disguised 404.

The Chat verification also ran after the Session/run mutation. A failed check
therefore left a claimed orphan run, which a later GET converted to
`RecoverableFailure`.

## Acceptance criteria

- A Session whose authenticated source differs from the Chat transport channel
  can start and retry its owning Chat run.
- User, persisted Chat ID, and logical Chat session mismatches still fail
  closed.
- A failed owning-Chat verification happens before a new Session/run mutation.
- Existing tenant/source/user/agent checks at the HTTP/store boundary remain
  unchanged.

## Tasks

1. Add service regression tests for distinct source/channel values and for
   mutation-free failure on Chat identity drift.
2. Remove the invalid source/channel equality check from
   `WPlusSopService._verified_owned_chat`.
3. Verify the owning Chat before persisting a new entry Session or a
   run-starting command.
4. Run targeted W+ service/router tests, Python lint/type checks applicable to
   the files, the frontend W+ tests, and GitNexus `detect-changes`.

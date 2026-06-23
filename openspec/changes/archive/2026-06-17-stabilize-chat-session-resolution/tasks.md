## 1. Implementation

- [x] 1.1 Inspect current task navigation, URL parsing, session initialization, and paginated history behavior.
- [x] 1.2 Add a fallback in `ChatSessionInitializer` so valid `/chat/:id` routes outside the loaded `sessions` page still become the runtime `currentSessionId`.
- [x] 1.3 Avoid mutating the loaded history `sessions` list during the fallback.
- [x] 1.4 Preserve active local pending sessions during new-chat first-response resolution.

## 2. Tests

- [x] 2.1 Preserve existing behavior for sessions already present in the loaded page.
- [x] 2.2 Cover selecting a deep-linked session outside the current loaded page.
- [x] 2.3 Cover not replacing an active local pending session during backend id resolution.

## 3. Verification

- [x] 3.1 Run `pnpm --dir console test:run src/pages/Chat/components/ChatSessionInitializer/index.test.tsx`.
- [x] 3.2 Run `pnpm --dir console exec tsc -b --noEmit`.
- [x] 3.3 Run GitNexus impact analysis before editing `ChatSessionInitializer`.
- [x] 3.4 Run GitNexus `detect_changes()` after implementation.

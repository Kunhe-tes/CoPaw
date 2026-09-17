# Context References Design

## Goal

Extend the Console chat `@` overlay so a user can select Skills, callable MCP tools, and current-workspace files as typed, one-turn Context References.

## Discovery and presentation

Typing `@` loads only the current Agent's Skills and callable MCP tools. With a non-empty query, the Console debounces for roughly 200 ms and queries all three resource types. Results render in fixed order—Skills, MCP Tools, Files—omit empty groups, return at most four entries per group, and show one shared empty state when nothing matches.

Files are filename-only matches from the workspace `media` and `static` roots. They remain in one Files group, but use a root-prefixed relative path as secondary text to distinguish equal filenames. MCP tools use `server / tool` as their stable label and display their description as secondary text. The empty-query footer invites the user to continue typing to search tools and files.

The compact overlay keeps all candidate content left aligned, shortens row height and typography, clamps secondary text to one line, and permits vertical but never horizontal scrolling. It provides no tooltip for truncated text.

## Selection and request contract

The editor renders every chosen item as a typed, non-editable token. Selection is a deduplicated per-request set, keyed by type-specific stable identity; duplicate picks do not add tokens, while equal names of different types coexist. The set is cleared immediately after its request is created.

The Console submits structured Context References instead of deriving selection from displayed text. The backend revalidates every reference in the current effective tenant and Agent scope, then creates trusted instruction context:

- Skill selections retain existing explicit-use directives.
- MCP selections instruct the Main Agent to prefer the selected callable tool when appropriate, without requiring a call or granting permissions.
- File selections identify an existing `media` or `static` file for on-demand reading or analysis, without inlining content or binary data.

## Backend discovery cache

A process-local Context Reference Directory Cache is keyed by effective tenant and Agent identity. It contains only discovery metadata and a filename index, never file contents; it is neither cross-process nor cross-scope.

Entries are created lazily when a user opens the `@` overlay. Skills have a fixed five-minute TTL. Callable MCP tools and merged file indexes use fixed three-minute TTLs. TTL is the only invalidation mechanism in this release; configuration and filesystem writes do not evict cache entries early. On expiry, refresh failure returns no results for that category—old data is never served. Final selection validation remains mandatory.

The cache holds 128 scope entries, drops expired entries during access, and evicts least-recently-used entries when full. Miss and expiry refreshes are single-flight per scope and category. `media` and `static` independently index the 5,000 most recently modified files at most.

MCP discovery runs concurrently, allows two seconds per server, and waits no more than three seconds overall. Failed and timed-out servers remain silent and contribute no tools.

## Testing

Tests cover typed selection, query behavior, compact group rendering, cache TTL/LRU/single-flight isolation, MCP timeout and silent failure, filename-only file search/capacity, request injection, and final scope validation.

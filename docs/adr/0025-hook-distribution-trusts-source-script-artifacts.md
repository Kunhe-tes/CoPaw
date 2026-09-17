# Hook Distribution Trusts Source Script Artifacts

**Status:** Accepted. An Agent Profile Hook Distribution copies the selected source scripts to each target tenant without a target-side safety scan. The source script's existing controlled-library validation and acceptance form the distribution trust boundary; repeating the scan would make distribution outcomes depend on the target's current scan policy rather than the explicitly selected source artifact.

## Considered Options

- Re-scan every script at each target — rejected because it can block a distribution of an already accepted source artifact solely because the target's current policy differs.

## Consequences

Distribution must continue to copy only selected scripts from the controlled source library, enforce the existing target conflict and atomicity rules, and audit the transfer. It must not be implemented as a general arbitrary-file copy.

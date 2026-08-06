# W+ SOP MemoryCandidate complexity reduction

## Goal

Reduce `MemoryCandidate._validate_sanitized_memory_candidate` cognitive
complexity from 22 to at most 15 without changing validation order, error
messages, accepted payloads, or rejected payloads.

## Implementation

1. Add behavior-level regression tests for validation errors and precedence so
   refactoring cannot change the public validation contract.
2. Extract cohesive content, target/receipt, and status validation methods from
   the Pydantic `model_validator`. Keep the decorated validator as the ordered
   orchestration point returning `self`.
3. Run all W+ model tests to protect the validation semantics.
4. Run formatting/static checks available in the workspace and the broader W+
   SOP unit suite.
5. Review the diff for validation-order or contract drift, then run GitNexus
   `detect_changes` against `main`.

## Acceptance criteria

- The same external analyzer and quality gate that reported the issue verifies
  cognitive complexity `<= 15`; unit tests do not duplicate that analyzer.
- Existing validation behavior and messages remain unchanged.
- W+ SOP model and backend unit tests pass.
- No unrelated local modifications are overwritten.

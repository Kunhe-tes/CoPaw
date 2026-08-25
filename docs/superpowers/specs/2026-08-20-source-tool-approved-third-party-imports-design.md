# Approved Third-Party Imports for Source Tools

## Goal

Allow source-owned Python tools to import the approved third-party packages
`requests`, `PIL` (Pillow), `numpy`, and `pandas`, while preserving the
existing rejection of every other non-standard-library import.

## Scope

The upload validator will continue to inspect source code statically and will
not import or execute it during validation. It will accept an import when its
top-level module is either a Python standard-library module or one of the four
approved import roots. Submodules are included: for example,
`from PIL import Image` and `from numpy.linalg import norm` are valid.

The approved import root for the Pillow distribution is `PIL`, its conventional
Python import name. `Pillow` itself is not an importable module name and is not
added to the validation allowlist.

## Non-goals

- Installing packages from uploaded files or a `requirements.txt`.
- Allowing arbitrary packages already present in the runtime environment.
- Allowing dynamic imports through `__import__` or `importlib`.
- Changing the single-file upload limit or source-tool lifecycle.

## Error Handling

Imports outside the standard library and approved roots remain rejected during
upload with an error that explains the accepted categories.

## Tests

Unit tests will prove that each approved package root and a representative
submodule import are accepted. Existing validation tests will continue to prove
that an unapproved third-party import and dynamic imports are rejected.

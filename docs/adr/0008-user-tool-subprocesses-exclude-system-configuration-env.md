# User tool subprocesses exclude system configuration env

User-invoked tool subprocesses must not inherit Swe backend system configuration environment keys, including keys declared by `src/swe/config/envs/*.json`, because those keys may contain service credentials, internal endpoint configuration, or secret storage pointers. We filter the inherited subprocess environment by removing those backend-owned keys and isolation-sensitive runtime keys while preserving basic shell execution needs such as command lookup and the Python path guard variables used to enforce workspace isolation.

## Considered Options

- Inherit the backend process environment unchanged: rejected because shell commands, command hooks, and MCP stdio processes can print or consume backend-owned configuration.
- Redact or blank sensitive inherited variables: rejected because key presence still reveals backend configuration shape and blank values can be misinterpreted as valid configuration.
- Block user commands from defining the same names themselves: rejected because that would require parsing shell semantics and would not address the inherited-environment leak.

## Consequences

User tool subprocesses see a smaller inherited environment than the Swe backend process. Users may still define same-named variables inside their own commands, and Swe runtime guard variables that protect subprocess execution remain available.

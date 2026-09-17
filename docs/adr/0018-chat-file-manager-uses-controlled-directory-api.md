# Chat file manager uses a controlled directory API

The chat header opens a dedicated File Manager overlay rather than extending the existing flat generated-files drawer. Its directory operations use a root- and path-controlled backend API, while the recycle-bin view adapts the existing governance archive instead of exposing the `governance` filesystem root; this keeps tenant path validation and directory-specific permissions at one boundary while preserving the chat UI scope.

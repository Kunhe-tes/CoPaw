interface ContentOnlySessionNotFoundOptions {
  enabled: boolean;
  error: unknown;
  requestedSessionId: string | undefined;
  currentSessionId: string | undefined;
}

export function isSessionNotFoundError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error as Error & { status?: number }).status === 404
  );
}

export function shouldShowContentOnlySessionNotFound({
  enabled,
  error,
  requestedSessionId,
  currentSessionId,
}: ContentOnlySessionNotFoundOptions): boolean {
  return Boolean(
    enabled &&
      requestedSessionId &&
      requestedSessionId === currentSessionId &&
      isSessionNotFoundError(error),
  );
}

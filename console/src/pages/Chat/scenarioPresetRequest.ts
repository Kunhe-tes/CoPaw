/** Whether a queued new-chat scenario must be consumed after one response. */
export function shouldClearPendingScenarioPreset(status?: number): boolean {
  return (
    status !== undefined && ((status >= 200 && status < 300) || status === 409)
  );
}

export function isShareableTurn(
  turnId: string,
  statuses: Record<string, string>,
): boolean {
  return Boolean(turnId) && statuses[turnId] === "completed";
}

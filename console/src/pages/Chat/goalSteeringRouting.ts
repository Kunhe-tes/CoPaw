const GOAL_STEERING_STATES = new Set(["ACTIVE", "WAITING"]);

export function shouldRouteGoalRequestAsSteering({
  goalState,
  hasExplicitGoalId,
}: {
  goalState: string | null | undefined;
  hasExplicitGoalId: boolean;
}): boolean {
  return !hasExplicitGoalId && GOAL_STEERING_STATES.has(goalState);
}

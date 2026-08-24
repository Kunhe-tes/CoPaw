import { describe, expect, it } from "vitest";
import { shouldRouteGoalRequestAsSteering } from "./goalSteeringRouting";

describe("shouldRouteGoalRequestAsSteering", () => {
  it("keeps an explicit Goal turn on the Runner path", () => {
    expect(
      shouldRouteGoalRequestAsSteering({
        goalState: "ACTIVE",
        hasExplicitGoalId: true,
      }),
    ).toBe(false);
  });

  it("routes ordinary input to an active Goal as Steering", () => {
    expect(
      shouldRouteGoalRequestAsSteering({
        goalState: "ACTIVE",
        hasExplicitGoalId: false,
      }),
    ).toBe(true);
  });
});

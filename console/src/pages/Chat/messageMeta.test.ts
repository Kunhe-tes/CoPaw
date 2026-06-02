import { describe, expect, it } from "vitest";
import {
  extractPlanInteractionCard,
  formatMessageTime,
  resolveGroupTimestamp,
  resolveMessageTimestamp,
} from "./messageMeta";

describe("messageMeta", () => {
  it("uses the backend-provided timestamp field", () => {
    const timestamp = resolveMessageTimestamp({
      timestamp: "2026-04-17T08:00:00Z",
    });

    expect(timestamp).toBeTypeOf("number");
    expect(formatMessageTime(timestamp)).toBe("04-17 16:00");
  });

  it("uses the latest backend-provided timestamp in a grouped response", () => {
    const timestamp = resolveGroupTimestamp([
      { timestamp: "2026-04-17T08:00:00Z" },
      { timestamp: "2026-04-17T09:30:00Z" },
    ]);

    expect(timestamp).toBe(
      resolveMessageTimestamp({ timestamp: "2026-04-17T09:30:00Z" }),
    );
    expect(formatMessageTime(timestamp)).toBe("04-17 17:30");
  });

  it("extracts validated plan interaction cards from nested metadata", () => {
    expect(
      extractPlanInteractionCard({
        metadata: {
          metadata: {
            plan_interaction_card: {
              card_type: "plan_review",
              plan_id: "plan-123",
              title: "Fix bug",
              summary: "Patch safely",
              steps: ["Read"],
              risks: [],
              verification: ["Test"],
              open_questions: [],
              confidence: 0.8,
            },
          },
        },
      }),
    ).toMatchObject({
      card_type: "plan_review",
      plan_id: "plan-123",
    });

    expect(
      extractPlanInteractionCard({
        metadata: {
          plan_interaction_card: {
            card_type: "plan_review",
            plan_id: "frontend-snapshot",
            title: "Invalid",
          },
        },
      }),
    ).toBeNull();
  });

  it("preserves clarification custom response permission", () => {
    expect(
      extractPlanInteractionCard({
        metadata: {
          plan_interaction_card: {
            card_type: "plan_clarification",
            kind: "single_choice",
            prompt: "Pick scope",
            allow_custom_response: true,
            options: [{ id: "small", label: "Small" }],
          },
        },
      }),
    ).toMatchObject({
      card_type: "plan_clarification",
      allow_custom_response: true,
    });
  });

  it("extracts structured clarification forms", () => {
    const card = extractPlanInteractionCard({
      metadata: {
        plan_interaction_card: {
          card_type: "plan_clarification",
          kind: "form",
          form_id: "customer_plan_clarification",
          prompt: "Collect planning context",
          allow_custom_response: true,
          fields: [
            {
              id: "industry",
              label: "所在行业",
              type: "select",
              required: true,
              options: [{ id: "retail", label: "零售/电商" }],
            },
            {
              id: "current_challenges",
              label: "当前主要挑战",
              type: "textarea",
              placeholder: "请补充",
            },
          ],
        },
      },
    });

    expect(card).toMatchObject({
      card_type: "plan_clarification",
      kind: "form",
      form_id: "customer_plan_clarification",
      allow_custom_response: true,
    });
    expect(card?.card_type).toBe("plan_clarification");
    if (card?.card_type !== "plan_clarification") return;
    expect(card.fields).toHaveLength(2);
    expect(card.fields?.[0]).toMatchObject({
      id: "industry",
      type: "select",
      required: true,
    });
  });
});

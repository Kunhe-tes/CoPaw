import { eventMetadata } from "./eventMetadata";
import type {
  HookConfigDraft,
  HookEventName,
  HookHandlerType,
} from "./types";

export type EventSummary = {
  configured: boolean;
  groups: number;
  handlers: number;
  handlerLabels: string[];
};

const handlerLabels: Record<HookHandlerType, string> = {
  command: "Command",
  http: "HTTP",
  prompt: "Prompt",
};

export function getLifecycleEvents(_config: HookConfigDraft): HookEventName[] {
  return (Object.keys(eventMetadata) as HookEventName[]).sort(
    (left, right) => eventMetadata[left].order - eventMetadata[right].order,
  );
}

export function getEventSummary(
  config: HookConfigDraft,
  event: HookEventName,
): EventSummary {
  const groups = config.events[event] ?? [];
  const handlers = groups.flatMap((group) => group.hooks);

  return {
    configured: event in config.events,
    groups: groups.length,
    handlers: handlers.length,
    handlerLabels: handlers.map((handler) => handlerLabels[handler.type]),
  };
}

import type { IAgentScopeRuntimeWebUISession } from "@/components/agentscope-chat";

type SessionWithIdentity = IAgentScopeRuntimeWebUISession & {
  realId?: string;
  sessionId?: string;
};

function identityKeys(session: IAgentScopeRuntimeWebUISession): string[] {
  const extended = session as SessionWithIdentity;
  return [extended.id, extended.realId, extended.sessionId].filter(
    (value): value is string => Boolean(value),
  );
}

function sessionsMatch(
  left: IAgentScopeRuntimeWebUISession,
  right: IAgentScopeRuntimeWebUISession,
): boolean {
  const rightKeys = new Set(identityKeys(right));
  return identityKeys(left).some((key) => rightKeys.has(key));
}

export function mergeConcurrentSessions(
  incoming: IAgentScopeRuntimeWebUISession[],
  current: IAgentScopeRuntimeWebUISession[],
  preserveCurrentDetails: boolean,
): IAgentScopeRuntimeWebUISession[] {
  const currentOnly = current.filter(
    (currentSession) =>
      !incoming.some((incomingSession) =>
        sessionsMatch(currentSession, incomingSession),
      ),
  );
  const mergedIncoming = incoming.map((incomingSession) => {
    const currentSession = current.find((candidate) =>
      sessionsMatch(candidate, incomingSession),
    );
    if (!currentSession) return incomingSession;

    const merged = preserveCurrentDetails
      ? { ...incomingSession, ...currentSession }
      : { ...currentSession, ...incomingSession };
    merged.messages = currentSession.messages;
    if (Object.prototype.hasOwnProperty.call(currentSession, "generating")) {
      merged.generating = currentSession.generating;
    }
    return merged;
  });

  return [...currentOnly, ...mergedIncoming];
}

function getVoiceRecorderUserWhitelist(): readonly string[] {
  if (typeof window === "undefined") {
    return [];
  }

  const whitelist = window.__env__?.voiceRecorderUserWhitelist;
  return Array.isArray(whitelist) ? whitelist : [];
}

export function isVoiceRecorderUserAllowed(userId?: string | null): boolean {
  const whitelist = getVoiceRecorderUserWhitelist();
  if (whitelist.includes("*")) {
    return true;
  }
  if (!userId) {
    return false;
  }
  return whitelist.includes(userId);
}

export function shouldShowGlobalVoiceRecorder(
  userId: string | null,
  showContentOnly: boolean,
  isOriginY: boolean,
): boolean {
  return !showContentOnly && !isOriginY && isVoiceRecorderUserAllowed(userId);
}

export function needsChatRecorderClearance(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

export function isOriginYSearch(search: string): boolean {
  return new URLSearchParams(search).get("origin") === "Y";
}

type TaskTabsRuntimeEnv = {
  enableOriginYTaskTabs?: unknown;
};

export function isRuntimeTaskTabsEnabled(
  env: TaskTabsRuntimeEnv | null | undefined,
): boolean {
  const value = env?.enableOriginYTaskTabs;
  return value === true || value === "true" || value === "1" || value === 1;
}

export function shouldEnableOriginYTaskTabs(
  search: string,
  env: TaskTabsRuntimeEnv | null | undefined =
    typeof window === "undefined" ? undefined : window.__env__,
): boolean {
  return isOriginYSearch(search) && isRuntimeTaskTabsEnabled(env);
}

const SUGGESTIONS_DISABLED_SOURCES = new Set(["ruice", "WDYT"]);

export function isSuggestionsDisabledForSource(source?: string | null): boolean {
  return SUGGESTIONS_DISABLED_SOURCES.has((source ?? "").trim().toLowerCase());
}

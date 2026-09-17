import type { MarketExpert } from "../../api/modules/market";

export function matchesExpertSearch(
  expert: MarketExpert,
  query: string,
): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  return [expert.name, expert.description, expert.creator_name].some((value) =>
    value.toLowerCase().includes(normalizedQuery),
  );
}

export function countExpertBbkIds(
  experts: MarketExpert[],
): Map<string, number> {
  const counts = new Map<string, number>();
  experts.forEach((expert) => {
    expert.bbk_ids.forEach((bbkId) => {
      counts.set(bbkId, (counts.get(bbkId) || 0) + 1);
    });
  });
  return counts;
}

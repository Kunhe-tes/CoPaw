export function getScrollTopAfterAnchorOffset({
  oldScrollTop,
  previousOffset,
  nextOffset,
}: {
  oldScrollTop: number;
  previousOffset: number;
  nextOffset: number;
}): number {
  return oldScrollTop + nextOffset - previousOffset;
}

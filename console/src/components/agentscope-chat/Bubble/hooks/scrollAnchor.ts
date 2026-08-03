export function getScrollTopAfterPrepend({
  clientHeight,
  newScrollHeight,
  oldScrollHeight,
  oldScrollTop,
  order,
}: {
  clientHeight: number;
  newScrollHeight: number;
  oldScrollHeight: number;
  oldScrollTop: number;
  order: "asc" | "desc";
}): number {
  const oldLogicalTop =
    order === "desc"
      ? oldScrollTop + oldScrollHeight - clientHeight
      : oldScrollTop;
  const newLogicalTop = oldLogicalTop + (newScrollHeight - oldScrollHeight);

  return order === "desc"
    ? newLogicalTop - newScrollHeight + clientHeight
    : newLogicalTop;
}

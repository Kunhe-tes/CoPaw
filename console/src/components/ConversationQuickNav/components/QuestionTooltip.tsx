interface QuestionTooltipProps {
  /** 问题序号 */
  index: number;
  /** 问题文本 */
  text: string;
  /** 是否显示 */
  visible: boolean;
  /** fixed 定位，避免被快速导航内部滚动区域裁剪 */
  position?: {
    top: number;
    right: number;
  };
}

export function QuestionTooltip({
  index,
  text,
  visible,
  position,
}: QuestionTooltipProps) {
  return (
    <div
      className={`quick-nav-tooltip ${visible ? "quick-nav-tooltip--visible" : ""}`}
      style={
        position
          ? {
              top: position.top,
              right: position.right,
            }
          : undefined
      }
    >
      <div className="quick-nav-tooltip-content">
        <strong># {index}</strong>
        <span>{text}</span>
      </div>
    </div>
  );
}

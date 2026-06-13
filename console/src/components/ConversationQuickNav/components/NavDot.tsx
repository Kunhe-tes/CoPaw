import React, { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { QuestionTooltip } from "./QuestionTooltip";

interface NavDotProps {
  /** 问题序号（1, 2, 3...） */
  index: number;
  /** 问题文本 */
  text: string;
  /** 消息 ID，用于跳转 */
  messageId: string;
  /** 点击回调 */
  onClick: (messageId: string) => void;
  /** 是否为当前活动的问题 */
  isCurrent?: boolean;
  /** 快速导航滚动容器，用于在滚动时刷新 tooltip 位置 */
  navScrollRef?: RefObject<HTMLElement | null>;
}

export function NavDot({
  index,
  text,
  messageId,
  onClick,
  isCurrent = false,
  navScrollRef,
}: NavDotProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<{
    top: number;
    right: number;
  }>();
  const dotRef = useRef<HTMLDivElement | null>(null);

  const updateTooltipPosition = useCallback(() => {
    const rect = dotRef.current?.getBoundingClientRect();
    if (rect) {
      setTooltipPosition({
        top: rect.top + rect.height / 2,
        right: window.innerWidth - rect.left + 12,
      });
    }
  }, []);

  const showTooltip = () => {
    updateTooltipPosition();
    setIsHovered(true);
  };

  const hideTooltip = () => {
    setIsHovered(false);
  };

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    onClick(messageId);
  };

  useEffect(() => {
    if (!isHovered) return;

    const scrollContainer = navScrollRef?.current;
    scrollContainer?.addEventListener("scroll", updateTooltipPosition, {
      passive: true,
    });
    window.addEventListener("resize", updateTooltipPosition);

    return () => {
      scrollContainer?.removeEventListener("scroll", updateTooltipPosition);
      window.removeEventListener("resize", updateTooltipPosition);
    };
  }, [isHovered, navScrollRef, updateTooltipPosition]);

  // 当前活动或hover时显示蓝色
  const isActive = isCurrent || isHovered;

  return (
    <div
      ref={dotRef}
      className={`quick-nav-dot ${isActive ? "quick-nav-dot--active" : ""}`}
      data-message-id={messageId}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
      onClick={handleClick}
      tabIndex={0}
      role="button"
      aria-label={`第 ${index} 次问题: ${text}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(messageId);
        }
      }}
    >
      <QuestionTooltip
        index={index}
        text={text}
        visible={isHovered}
        position={tooltipPosition}
      />
    </div>
  );
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useQuestionMessages } from "./hooks/useQuestionMessages";
import { useScrollToMessage } from "./hooks/useScrollToMessage";
import { useCurrentQuestion } from "./hooks/useCurrentQuestion";
import { NavDot } from "./components/NavDot";
import { ConversationQuickNavProps } from "./types";
import Style from "./style";

export default function ConversationQuickNav({
  minQuestions = 1,
  messages,
  scrollRootRef,
}: ConversationQuickNavProps) {
  const { questions, shouldShow } = useQuestionMessages(
    minQuestions,
    messages,
    scrollRootRef,
  );
  const { scrollToMessage } = useScrollToMessage(scrollRootRef);
  const { currentQuestionId, setCurrent } = useCurrentQuestion(
    questions,
    scrollRootRef,
  );
  const [isContainerHovered, setIsContainerHovered] = useState(false);
  const [hiddenQuestionCount, setHiddenQuestionCount] = useState({
    above: 0,
    below: 0,
  });
  const navScrollRef = useRef<HTMLDivElement | null>(null);

  const updateHiddenQuestionCount = useCallback(() => {
    const scrollContainer = navScrollRef.current;
    if (!scrollContainer) return;

    if (scrollContainer.scrollHeight <= scrollContainer.clientHeight + 1) {
      setHiddenQuestionCount((current) =>
        current.above === 0 && current.below === 0
          ? current
          : { above: 0, below: 0 },
      );
      return;
    }

    const itemPitch = 19;
    const verticalPadding = 28;
    const usableHeight = Math.max(
      itemPitch,
      scrollContainer.clientHeight - verticalPadding,
    );
    const visibleCount = Math.max(
      1,
      Math.floor((usableHeight + 15) / itemPitch),
    );
    const totalHidden = Math.max(0, questions.length - visibleCount);
    const remainingScroll =
      scrollContainer.scrollHeight -
      scrollContainer.clientHeight -
      scrollContainer.scrollTop;
    const above =
      remainingScroll <= 1
        ? totalHidden
        : Math.min(
            totalHidden,
            Math.floor(scrollContainer.scrollTop / itemPitch),
          );
    const below = Math.max(0, totalHidden - above);

    const next = {
      above: Math.min(questions.length, above),
      below: Math.min(questions.length, below),
    };
    setHiddenQuestionCount((current) =>
      current.above === next.above && current.below === next.below
        ? current
        : next,
    );
  }, [questions.length]);

  useEffect(() => {
    if (!currentQuestionId) return;

    const currentDot = Array.from(
      navScrollRef.current?.querySelectorAll<HTMLElement>(".quick-nav-dot") ??
        [],
    ).find((dot) => dot.dataset.messageId === currentQuestionId);
    currentDot?.scrollIntoView?.({
      block: "nearest",
      inline: "nearest",
    });
    requestAnimationFrame(updateHiddenQuestionCount);
  }, [currentQuestionId, updateHiddenQuestionCount]);

  useEffect(() => {
    const scrollContainer = navScrollRef.current;
    if (!scrollContainer) return;

    const frameId = requestAnimationFrame(updateHiddenQuestionCount);
    const resizeObserver = new ResizeObserver(updateHiddenQuestionCount);
    resizeObserver.observe(scrollContainer);

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
    };
  }, [questions.length, updateHiddenQuestionCount]);

  if (!shouldShow) {
    return null;
  }

  const handleClick = (messageId: string) => {
    // 点击后立即切换高亮
    setCurrent(messageId);
    scrollToMessage(messageId);
  };

  const scrollNavPage = (direction: -1 | 1) => {
    const scrollContainer = navScrollRef.current;
    if (!scrollContainer) return;

    const distance = Math.max(120, scrollContainer.clientHeight * 0.75);
    if (scrollContainer.scrollBy) {
      scrollContainer.scrollBy({
        top: direction * distance,
        behavior: "smooth",
      });
    } else {
      scrollContainer.scrollTop += direction * distance;
      updateHiddenQuestionCount();
    }
  };

  return (
    <>
      <Style />
      <div
        className={`conversation-quick-nav ${
          isContainerHovered ? "conversation-quick-nav--hovered" : ""
        }`}
        onMouseEnter={() => setIsContainerHovered(true)}
        onMouseLeave={() => setIsContainerHovered(false)}
      >
        <div
          ref={navScrollRef}
          className="conversation-quick-nav__scroll"
          aria-label="会话快速导航"
          onScroll={updateHiddenQuestionCount}
        >
          <div className="conversation-quick-nav__items">
            {questions.map((question) => {
              const isCurrent = question.id === currentQuestionId;
              return (
                <NavDot
                  key={question.id}
                  index={question.index}
                  text={question.text}
                  messageId={question.id}
                  onClick={handleClick}
                  isCurrent={isCurrent}
                  navScrollRef={navScrollRef}
                />
              );
            })}
          </div>
        </div>
        {hiddenQuestionCount.above > 0 && (
          <button
            type="button"
            className="quick-nav-overflow-hint quick-nav-overflow-hint--top"
            onClick={() => scrollNavPage(-1)}
            aria-label={`上方还有 ${hiddenQuestionCount.above} 个问题`}
          >
            <ChevronUp size={13} aria-hidden="true" />
            <span>上方还有 {hiddenQuestionCount.above} 条</span>
          </button>
        )}
        {hiddenQuestionCount.below > 0 && (
          <button
            type="button"
            className="quick-nav-overflow-hint quick-nav-overflow-hint--bottom"
            onClick={() => scrollNavPage(1)}
            aria-label={`下方还有 ${hiddenQuestionCount.below} 个问题`}
          >
            <span>下方还有 {hiddenQuestionCount.below} 条</span>
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        )}
      </div>
    </>
  );
}

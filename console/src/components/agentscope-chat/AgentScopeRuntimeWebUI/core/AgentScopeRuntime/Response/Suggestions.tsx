import React, { useState } from "react";
import { Tooltip } from "antd";
import { useProviderContext } from "@/components/agentscope-chat";
import { useIframeStore } from "@/stores/iframeStore";
import { isSuggestionsDisabledForSource } from "@/utils/sourceFeatures";
import { SparkRightArrowLine } from "@agentscope-ai/icons";
import { AgentScopeRuntimeRunStatus } from "../types";
import { emit } from "../../Context/useChatAnywhereEventEmitter";
import Style from "./style";

export interface ISuggestionsProps {
  /**
   * @description 建议问题列表
   */
  suggestions: string[];
  /**
   * @description 当前响应状态
   */
  status: AgentScopeRuntimeRunStatus;
}

export default function Suggestions(props: ISuggestionsProps) {
  const { suggestions, status } = props;
  const prefixCls = useProviderContext().getPrefixCls("suggestions");
  const source = useIframeStore((state) => state.source);
  const [tooltipVisible, setTooltipVisible] = useState<string | null>(null);

  // 没有建议内容时不渲染
  if (!suggestions?.length || isSuggestionsDisabledForSource(source)) {
    return null;
  }

  // 是否正在生成响应
  const isGenerating = status === AgentScopeRuntimeRunStatus.InProgress;

  const handleClick = (query: string) => {
    if (isGenerating) {
      // 正在生成时显示提示，不发起提问
      setTooltipVisible(query);
      setTimeout(() => setTooltipVisible(null), 1500);
      return;
    }
    // Suggestions are rendered only after a response is finished. Use a
    // dedicated event so stale session.generating state cannot block submit.
    emit({
      type: "handleSuggestionSubmit",
      data: { query, fileList: [] },
    });
  };

  return (
    <>
      <Style />
      <div className={prefixCls}>
        <div className={`${prefixCls}-header`}>
          <div className={`${prefixCls}-label`}>猜你想问</div>
        </div>
        <div className={`${prefixCls}-list`}>
          {suggestions.map((suggestion, index) => (
            <Tooltip
              key={suggestion}
              title={tooltipVisible === suggestion ? "正在回复中，请稍候..." : ""}
              open={tooltipVisible === suggestion || undefined}
              mouseEnterDelay={0.3}
            >
              <button
                type="button"
                className={`${prefixCls}-item`}
                onClick={() => handleClick(suggestion)}
              >
                <span className={`${prefixCls}-item-text`}>
                  {suggestion}
                </span>
                <SparkRightArrowLine className={`${prefixCls}-item-icon`} />
              </button>
            </Tooltip>
          ))}
        </div>
      </div>
    </>
  );
}

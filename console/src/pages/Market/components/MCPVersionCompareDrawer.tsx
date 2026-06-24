/**
 * 市场 MCP 版本比对 Drawer。
 *
 * 与 Skills/VersionCompareDrawer 对称，但 MCP 只有 mcp.json 一个文件，
 * 所以省略左侧文件树、文件导航；保留 IDEA 风格 side-by-side diff、
 * 差异块导航、全屏切换、滚动同步。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloseOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  MinusOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import * as Diff from "diff";
import {
  marketMcpVersionApi,
  MCPVersionCompareResult,
} from "../../../api/modules/marketMcpVersion";

const { Text } = Typography;

interface MCPVersionCompareDrawerProps {
  open: boolean;
  sourceId: string;
  itemId: string;
  baseVersion: string;
  targetVersion: string;
  onClose: () => void;
}

interface DiffLine {
  type: "added" | "removed" | "normal";
  content: string;
  originalLineNumber?: number;
  modifiedLineNumber?: number;
}

interface DiffBlock {
  startOriginal: number;
  endOriginal: number;
  startModified: number;
  endModified: number;
}

function computeLineDiff(
  originalContent: string,
  modifiedContent: string,
): {
  originalLines: DiffLine[];
  modifiedLines: DiffLine[];
  diffBlocks: DiffBlock[];
} {
  const diffResult = Diff.diffLines(originalContent, modifiedContent);
  const originalLines: DiffLine[] = [];
  const modifiedLines: DiffLine[] = [];
  const diffBlocks: DiffBlock[] = [];

  let originalLineNum = 0;
  let modifiedLineNum = 0;
  let currentBlock: DiffBlock | null = null;

  diffResult.forEach((part) => {
    const lines = part.value.split("\n");
    if (lines.length > 0 && lines[lines.length - 1] === "") {
      lines.pop();
    }

    if (part.added) {
      const startModified = modifiedLineNum + 1;
      lines.forEach((line) => {
        modifiedLineNum++;
        modifiedLines.push({
          type: "added",
          content: line,
          modifiedLineNumber: modifiedLineNum,
        });
      });
      if (!currentBlock) {
        currentBlock = {
          startOriginal: -1,
          endOriginal: -1,
          startModified,
          endModified: modifiedLineNum,
        };
      } else {
        currentBlock.endModified = modifiedLineNum;
      }
    } else if (part.removed) {
      const startOriginal = originalLineNum + 1;
      lines.forEach((line) => {
        originalLineNum++;
        originalLines.push({
          type: "removed",
          content: line,
          originalLineNumber: originalLineNum,
        });
      });
      if (!currentBlock) {
        currentBlock = {
          startOriginal,
          endOriginal: originalLineNum,
          startModified: -1,
          endModified: -1,
        };
      } else {
        currentBlock.endOriginal = originalLineNum;
      }
    } else {
      if (currentBlock) {
        diffBlocks.push(currentBlock);
        currentBlock = null;
      }
      lines.forEach((line) => {
        originalLineNum++;
        modifiedLineNum++;
        originalLines.push({
          type: "normal",
          content: line,
          originalLineNumber: originalLineNum,
          modifiedLineNumber: modifiedLineNum,
        });
        modifiedLines.push({
          type: "normal",
          content: line,
          originalLineNumber: originalLineNum,
          modifiedLineNumber: modifiedLineNum,
        });
      });
    }
  });

  if (currentBlock) {
    diffBlocks.push(currentBlock);
  }

  return { originalLines, modifiedLines, diffBlocks };
}

function LineNumbers({
  lines,
  side,
  maxWidth,
}: {
  lines: DiffLine[];
  side: "left" | "right";
  maxWidth: number;
}) {
  return (
    <div
      style={{
        padding: "0 8px",
        backgroundColor: "#f6f8fa",
        minWidth: maxWidth,
        textAlign: "right",
        fontFamily: "'SF Mono', Consolas, monospace",
        fontSize: 12,
        lineHeight: "20px",
        color: "#6e7781",
        userSelect: "none",
        flexShrink: 0,
      }}
    >
      {lines.map((line, idx) => {
        const lineNum =
          side === "left"
            ? line.originalLineNumber
            : line.modifiedLineNumber;
        const bgColor =
          line.type === "removed"
            ? "#ffeef0"
            : line.type === "added"
              ? "#e6ffed"
              : "transparent";
        return (
          <div
            key={idx}
            style={{
              height: "20px",
              lineHeight: "20px",
              backgroundColor: bgColor,
            }}
          >
            {lineNum || ""}
          </div>
        );
      })}
    </div>
  );
}

function DiffGutter({
  originalLines,
  modifiedLines,
}: {
  originalLines: DiffLine[];
  modifiedLines: DiffLine[];
}) {
  const gutterLines: { type: "added" | "removed" | "normal" }[] = [];
  let origIdx = 0;
  let modIdx = 0;

  while (origIdx < originalLines.length || modIdx < modifiedLines.length) {
    const orig = originalLines[origIdx];
    const mod = modifiedLines[modIdx];

    if (orig && orig.type === "removed") {
      gutterLines.push({ type: "removed" });
      origIdx++;
    } else if (mod && mod.type === "added") {
      gutterLines.push({ type: "added" });
      modIdx++;
    } else if (
      orig &&
      mod &&
      orig.type === "normal" &&
      mod.type === "normal"
    ) {
      gutterLines.push({ type: "normal" });
      origIdx++;
      modIdx++;
    } else {
      break;
    }
  }

  return (
    <div
      style={{
        width: 32,
        flexShrink: 0,
        backgroundColor: "#f0f0f0",
        borderLeft: "1px solid #e1e4e8",
        borderRight: "1px solid #e1e4e8",
      }}
    >
      {gutterLines.map((line, idx) => {
        const bgColor =
          line.type === "added"
            ? "#acf2bd"
            : line.type === "removed"
              ? "#fdb8c0"
              : "transparent";
        const symbol =
          line.type === "added" ? "+" : line.type === "removed" ? "-" : " ";
        return (
          <div
            key={idx}
            style={{
              height: "20px",
              lineHeight: "20px",
              backgroundColor: bgColor,
              textAlign: "center",
              fontFamily: "'SF Mono', Consolas, monospace",
              fontSize: 11,
              color: line.type === "normal" ? "transparent" : "#cb2431",
              userSelect: "none",
            }}
          >
            {symbol}
          </div>
        );
      })}
    </div>
  );
}

function CodeContent({
  lines,
  side,
}: {
  lines: DiffLine[];
  side: "left" | "right";
}) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {lines.map((line, idx) => {
        const lineNum =
          side === "left"
            ? line.originalLineNumber
            : line.modifiedLineNumber;
        const bgColor =
          line.type === "removed"
            ? "#ffeef0"
            : line.type === "added"
              ? "#e6ffed"
              : "transparent";
        return (
          <div
            key={idx}
            data-line={lineNum}
            data-original={line.originalLineNumber}
            data-modified={line.modifiedLineNumber}
            style={{
              height: "20px",
              lineHeight: "20px",
              padding: "0 12px",
              backgroundColor: bgColor,
              fontFamily: "'SF Mono', Consolas, monospace",
              fontSize: 13,
              whiteSpace: "pre",
              overflow: "hidden",
              textOverflow: "ellipsis",
              color: "#24292f",
            }}
          >
            {line.content || " "}
          </div>
        );
      })}
    </div>
  );
}

function DiffView({
  originalLines,
  modifiedLines,
  scrollToOriginal,
  onScroll,
  scrollSyncRef,
}: {
  originalLines: DiffLine[];
  modifiedLines: DiffLine[];
  scrollToOriginal?: number;
  onScroll?: (scrollTop: number) => void;
  scrollSyncRef?: React.MutableRefObject<number>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isScrollingRef = useRef(false);

  const maxLineNum = Math.max(
    ...originalLines.map((l) => l.originalLineNumber || 0),
    ...modifiedLines.map((l) => l.modifiedLineNumber || 0),
    1,
  );
  const lineNumberWidth = maxLineNum > 999 ? 50 : 40;

  useEffect(() => {
    if (scrollToOriginal && containerRef.current) {
      const selector = `[data-original="${scrollToOriginal}"]`;
      const el = containerRef.current.querySelector(selector);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [scrollToOriginal]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !onScroll) return;

    const handleScroll = () => {
      if (isScrollingRef.current) return;
      isScrollingRef.current = true;
      onScroll(container.scrollTop);
      requestAnimationFrame(() => {
        isScrollingRef.current = false;
      });
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, [onScroll]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !scrollSyncRef) return;

    const checkScrollSync = () => {
      if (isScrollingRef.current) return;
      const targetScroll = scrollSyncRef.current;
      if (Math.abs(container.scrollTop - targetScroll) > 2) {
        container.scrollTop = targetScroll;
      }
    };

    const intervalId = setInterval(checkScrollSync, 50);
    return () => clearInterval(intervalId);
  }, [scrollSyncRef]);

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1,
        overflow: "auto",
        backgroundColor: "#fff",
        minHeight: 0,
      }}
    >
      {originalLines.length === 0 && modifiedLines.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", color: "#6e7781" }}>
          <Text type="secondary">空文件</Text>
        </div>
      ) : (
        <div style={{ display: "flex" }}>
          <CodeContent lines={originalLines} side="left" />
          <LineNumbers
            lines={originalLines}
            side="left"
            maxWidth={lineNumberWidth}
          />
          <DiffGutter
            originalLines={originalLines}
            modifiedLines={modifiedLines}
          />
          <LineNumbers
            lines={modifiedLines}
            side="right"
            maxWidth={lineNumberWidth}
          />
          <CodeContent lines={modifiedLines} side="right" />
        </div>
      )}
    </div>
  );
}

export function MCPVersionCompareDrawer(props: MCPVersionCompareDrawerProps) {
  const { open, sourceId, itemId, baseVersion, targetVersion, onClose } =
    props;

  const [loading, setLoading] = useState(false);
  const [compareResult, setCompareResult] =
    useState<MCPVersionCompareResult | null>(null);
  const [currentDiffIndex, setCurrentDiffIndex] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);

  const scrollSyncRef = useRef<number>(0);

  const handleScrollSync = useCallback((scrollTop: number) => {
    scrollSyncRef.current = scrollTop;
  }, []);

  useEffect(() => {
    if (!open || !sourceId || !itemId) return;

    setLoading(true);
    setCurrentDiffIndex(0);

    marketMcpVersionApi
      .compareVersions(sourceId, itemId, baseVersion, targetVersion)
      .then((result) => {
        setCompareResult(result);
      })
      .catch((err) => {
        console.error("Failed to compare MCP versions:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [open, sourceId, itemId, baseVersion, targetVersion]);

  // MCP 单文件 → 取 files[0]，无文件时为空
  const file = compareResult?.files[0];

  const diffData = useMemo(() => {
    if (!file) return null;
    return computeLineDiff(file.original_content, file.modified_content);
  }, [file]);

  const handleNavigateDiff = (direction: "next" | "prev") => {
    if (!diffData || diffData.diffBlocks.length === 0) return;
    const newIndex =
      direction === "next"
        ? (currentDiffIndex + 1) % diffData.diffBlocks.length
        : (currentDiffIndex - 1 + diffData.diffBlocks.length) %
          diffData.diffBlocks.length;
    setCurrentDiffIndex(newIndex);
  };

  const currentBlock = diffData?.diffBlocks[currentDiffIndex];
  const scrollToOriginal =
    currentBlock && currentBlock.startOriginal > 0
      ? currentBlock.startOriginal
      : undefined;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={fullscreen ? "100%" : 1000}
      title={null}
      closable={false}
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          height: "100%",
        },
      }}
    >
      {/* 头部 */}
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid #e1e4e8",
          backgroundColor: "#f6f8fa",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <Text strong style={{ fontSize: 16, color: "#24292f" }}>
            MCP 版本比对
          </Text>
          <div
            style={{
              marginTop: 4,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Tag color="blue" style={{ borderRadius: 6 }}>
              {/^v/i.test(baseVersion) ? baseVersion : `v${baseVersion}`}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              →
            </Text>
            <Tag color="green" style={{ borderRadius: 6 }}>
              {/^v/i.test(targetVersion) ? targetVersion : `v${targetVersion}`}
            </Tag>
          </div>
        </div>
        <Space size={8}>
          <Tooltip title={fullscreen ? "退出全屏" : "全屏显示"}>
            <Button
              onClick={() => setFullscreen(!fullscreen)}
              icon={
                fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />
              }
              type="text"
              style={{ color: "#6e7781" }}
            />
          </Tooltip>
          <Button
            onClick={onClose}
            icon={<CloseOutlined />}
            type="text"
            style={{ color: "#6e7781" }}
          />
        </Space>
      </div>

      {/* 统计摘要 */}
      {compareResult && (
        <div
          style={{
            padding: "10px 20px",
            backgroundColor: "#fff",
            borderBottom: "1px solid #e1e4e8",
            display: "flex",
            gap: 16,
            alignItems: "center",
          }}
        >
          <Text style={{ fontSize: 13, color: "#24292f" }}>
            <Text strong>{compareResult.stats.changed_files}</Text> 个文件变更
          </Text>
          <Text style={{ fontSize: 13, color: "#28a745" }}>
            <PlusOutlined style={{ marginRight: 4 }} />+
            {compareResult.stats.added_lines}
          </Text>
          <Text style={{ fontSize: 13, color: "#cb2431" }}>
            <MinusOutlined style={{ marginRight: 4 }} />-
            {compareResult.stats.deleted_lines}
          </Text>
        </div>
      )}

      {/* 主体 */}
      <div
        style={{
          display: "flex",
          flex: 1,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        {loading ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <Spin size="large" />
          </div>
        ) : !file ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <Empty description="无文件差异" />
          </div>
        ) : (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              minWidth: 0,
              overflow: "hidden",
            }}
          >
            {/* 文件标题 + 差异导航 */}
            <div
              style={{
                padding: "8px 16px",
                borderBottom: "1px solid #e1e4e8",
                backgroundColor: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <Text strong style={{ fontSize: 13, color: "#24292f" }}>
                  {file.path}
                </Text>
                {file.added_lines > 0 && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "#28a745",
                      fontWeight: 500,
                    }}
                  >
                    +{file.added_lines}
                  </span>
                )}
                {file.deleted_lines > 0 && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "#cb2431",
                      fontWeight: 500,
                    }}
                  >
                    -{file.deleted_lines}
                  </span>
                )}
              </div>

              {diffData && diffData.diffBlocks.length > 0 && (
                <Space size={8}>
                  <Button
                    size="small"
                    onClick={() => handleNavigateDiff("prev")}
                    icon={<ArrowUpOutlined />}
                  >
                    {currentDiffIndex + 1}/{diffData.diffBlocks.length}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => handleNavigateDiff("next")}
                    icon={<ArrowDownOutlined />}
                  />
                </Space>
              )}
            </div>

            <DiffView
              originalLines={diffData?.originalLines || []}
              modifiedLines={diffData?.modifiedLines || []}
              scrollToOriginal={scrollToOriginal}
              onScroll={handleScrollSync}
              scrollSyncRef={scrollSyncRef}
            />
          </div>
        )}
      </div>
    </Drawer>
  );
}

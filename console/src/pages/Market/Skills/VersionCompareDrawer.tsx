import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  Drawer,
  Tree,
  Button,
  Spin,
  Empty,
  Typography,
  Tag,
  Space,
  Tooltip,
} from "antd";
import type { TreeDataNode, TreeProps } from "antd";
import {
  FileOutlined,
  FolderOutlined,
  PlusOutlined,
  MinusOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  CloseOutlined,
  RightOutlined,
  DownOutlined,
} from "@ant-design/icons";
import * as Diff from "diff";
import { skillVersionApi, VersionCompareResult } from "../../../api/modules/skillVersion";

const { Text } = Typography;

interface VersionCompareDrawerProps {
  open: boolean;
  sourceId: string;
  itemId: string;
  baseVersion: string;
  targetVersion: string;
  onClose: () => void;
}

type FileChangeType = "added" | "deleted" | "modified" | "unchanged";

interface FileNode {
  path: string;
  changeType: FileChangeType;
  addedLines: number;
  deletedLines: number;
  originalContent: string;
  modifiedContent: string;
}

interface DiffLine {
  type: "added" | "removed" | "normal";
  content: string;
  originalLineNumber?: number;
  modifiedLineNumber?: number;
}

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const langMap: Record<string, string> = {
    md: "markdown",
    json: "json",
    js: "javascript",
    ts: "typescript",
    tsx: "typescript",
    jsx: "javascript",
    py: "python",
    yaml: "yaml",
    yml: "yaml",
    xml: "xml",
    html: "html",
    css: "css",
    scss: "scss",
    less: "less",
    sql: "sql",
    sh: "bash",
    txt: "plaintext",
  };
  return langMap[ext] || "plaintext";
}

function convertCompareResultToFiles(result: VersionCompareResult): FileNode[] {
  return result.files.map((file) => {
    let changeType: FileChangeType;
    if (file.added_lines === 0 && file.deleted_lines === 0) {
      changeType = "unchanged";
    } else if (file.added_lines > 0 && file.deleted_lines === 0) {
      changeType = "added";
    } else if (file.deleted_lines > 0 && file.added_lines === 0) {
      changeType = "deleted";
    } else {
      changeType = "modified";
    }

    return {
      path: file.path,
      changeType,
      addedLines: file.added_lines,
      deletedLines: file.deleted_lines,
      originalContent: file.original_content || "",
      modifiedContent: file.modified_content || "",
    };
  });
}

function getChangeIcon(changeType: FileChangeType): React.ReactNode {
  switch (changeType) {
    case "added":
      return <PlusOutlined style={{ color: "#28a745", fontSize: 12 }} />;
    case "deleted":
      return <MinusOutlined style={{ color: "#cb2431", fontSize: 12 }} />;
    case "modified":
      return <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "#b08800" }} />;
    case "unchanged":
      return null;
    default:
      return null;
  }
}

function getChangeColor(changeType: FileChangeType): string {
  switch (changeType) {
    case "added":
      return "#28a745";
    case "deleted":
      return "#cb2431";
    case "modified":
      return "#b08800";
    case "unchanged":
      return "#6e7781";
    default:
      return "#6e7781";
  }
}

/**
 * 构建树形目录结构（VSCode风格）
 */
function buildFileTree(files: FileNode[]): TreeDataNode[] {
  const nodeMap: Map<string, TreeDataNode> = new Map();

  files.forEach((file) => {
    const parts = file.path.split("/");

    // 构建文件夹节点
    for (let i = 0; i < parts.length - 1; i++) {
      const folderPath = parts.slice(0, i + 1).join("/");
      const folderName = parts[i];

      if (!nodeMap.has(folderPath)) {
        const childFiles = files.filter((f) => f.path.startsWith(folderPath + "/"));
        const hasChanges = childFiles.some((f) => f.changeType !== "unchanged");
        const addedCount = childFiles.filter((f) => f.changeType === "added").length;
        const deletedCount = childFiles.filter((f) => f.changeType === "deleted").length;
        const modifiedCount = childFiles.filter((f) => f.changeType === "modified").length;

        // 简化的 title 渲染
        let titleText = folderName;
        if (addedCount > 0 || deletedCount > 0 || modifiedCount > 0) {
          const stats = [];
          if (addedCount > 0) stats.push(`+${addedCount}`);
          if (deletedCount > 0) stats.push(`-${deletedCount}`);
          if (modifiedCount > 0) stats.push(`~${modifiedCount}`);
          titleText = `${folderName}  ${stats.join(" ")}`;
        }

        nodeMap.set(folderPath, {
          key: folderPath,
          title: titleText,
          icon: <FolderOutlined style={{ color: hasChanges ? "#b08800" : "#6e7781", fontSize: 14 }} />,
          children: [],
        });
      }
    }

    // 构建文件节点
    const fileName = parts[parts.length - 1];
    let fileTitle = fileName;
    if (file.addedLines > 0 || file.deletedLines > 0) {
      const stats = [];
      if (file.addedLines > 0) stats.push(`+${file.addedLines}`);
      if (file.deletedLines > 0) stats.push(`-${file.deletedLines}`);
      fileTitle = `${fileName}  ${stats.join(" ")}`;
    }

    nodeMap.set(file.path, {
      key: file.path,
      title: fileTitle,
      icon: <FileOutlined style={{ color: getChangeColor(file.changeType), fontSize: 14 }} />,
      isLeaf: true,
    });
  });

  // 建立父子关系
  files.forEach((file) => {
    const parts = file.path.split("/");
    if (parts.length === 1) return;

    const parentPath = parts.slice(0, parts.length - 1).join("/");
    const parentNode = nodeMap.get(parentPath);
    const fileNode = nodeMap.get(file.path);

    if (parentNode && fileNode && parentNode.children) {
      if (!parentNode.children.some((c) => c.key === file.path)) {
        parentNode.children.push(fileNode);
      }
    }
  });

  // 添加文件夹到父文件夹
  const folderPaths = Array.from(nodeMap.keys())
    .filter((key) => !nodeMap.get(key)?.isLeaf)
    .sort((a, b) => a.split("/").length - b.split("/").length);

  folderPaths.forEach((folderPath) => {
    const parts = folderPath.split("/");
    if (parts.length === 1) return;

    const parentPath = parts.slice(0, parts.length - 1).join("/");
    const parentNode = nodeMap.get(parentPath);
    const folderNode = nodeMap.get(folderPath);

    if (parentNode && folderNode && parentNode.children) {
      if (!parentNode.children.some((c) => c.key === folderPath)) {
        parentNode.children.push(folderNode);
      }
    }
  });

  // 提取根节点并排序
  const rootNodes: TreeDataNode[] = [];
  nodeMap.forEach((node, key) => {
    if (key.split("/").length === 1) {
      rootNodes.push(node);
    }
  });

  // 排序：文件夹在前，文件在后；同类型按名称排序
  const sortChildren = (nodes: TreeDataNode[]) => {
    nodes.sort((a, b) => {
      const aIsLeaf = a.isLeaf;
      const bIsLeaf = b.isLeaf;
      if (aIsLeaf !== bIsLeaf) return aIsLeaf ? 1 : -1;
      const aName = (a.key as string).split("/").pop() || "";
      const bName = (b.key as string).split("/").pop() || "";
      return aName.localeCompare(bName);
    });
    nodes.forEach((node) => {
      if (node.children && node.children.length > 0) {
        sortChildren(node.children);
      }
    });
  };

  sortChildren(rootNodes);
  return rootNodes;
}

/**
 * 差异块（连续改动聚合）
 */
interface DiffBlock {
  type: "change";  // 统一标记为变更块
  startOriginal: number;  // 原文件起始行（-1表示新增块）
  endOriginal: number;    // 原文件结束行
  startModified: number;  // 新文件起始行（-1表示删除块）
  endModified: number;    // 新文件结束行
}

/**
 * 计算行级差异，并聚合为差异块
 */
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

  // 当前差异块追踪
  let currentBlock: DiffBlock | null = null;

  diffResult.forEach((part) => {
    const lines = part.value.split("\n");
    if (lines.length > 0 && lines[lines.length - 1] === "") {
      lines.pop();
    }

    if (part.added) {
      // 新增行：记录差异块起始
      const startModified = modifiedLineNum + 1;
      lines.forEach((line) => {
        modifiedLineNum++;
        modifiedLines.push({
          type: "added",
          content: line,
          modifiedLineNumber: modifiedLineNum,
        });
      });
      // 创建或更新差异块
      if (!currentBlock) {
        currentBlock = {
          type: "change",
          startOriginal: -1,
          endOriginal: -1,
          startModified,
          endModified: modifiedLineNum,
        };
      } else {
        // 延伸当前差异块
        currentBlock.endModified = modifiedLineNum;
      }
    } else if (part.removed) {
      // 删除行：记录差异块起始
      const startOriginal = originalLineNum + 1;
      lines.forEach((line) => {
        originalLineNum++;
        originalLines.push({
          type: "removed",
          content: line,
          originalLineNumber: originalLineNum,
        });
      });
      // 创建或更新差异块
      if (!currentBlock) {
        currentBlock = {
          type: "change",
          startOriginal,
          endOriginal: originalLineNum,
          startModified: -1,
          endModified: -1,
        };
      } else {
        // 延伸当前差异块（删除行在原文件侧）
        currentBlock.endOriginal = originalLineNum;
      }
    } else {
      // 未修改行：如果有未结束的差异块，保存它
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

  // 保存最后一个差异块
  if (currentBlock) {
    diffBlocks.push(currentBlock);
  }

  return { originalLines, modifiedLines, diffBlocks };
}

/**
 * 行号列组件（IDEA 风格：行号在外侧）
 */
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
        const lineNum = side === "left"
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

/**
 * 中间沟组件（IDEA 风格：显示变更类型指示器）
 */
function DiffGutter({
  originalLines,
  modifiedLines,
}: {
  originalLines: DiffLine[];
  modifiedLines: DiffLine[];
}) {
  // 按行配对，生成每行的变更状态
  const gutterLines: { type: "added" | "removed" | "modified" | "normal" }[] = [];
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
    } else if (orig && mod && orig.type === "normal" && mod.type === "normal") {
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
              : line.type === "modified"
                ? "#fdb8c0"
                : "transparent";
        const symbol =
          line.type === "added"
            ? "+"
            : line.type === "removed"
              ? "-"
              : " ";
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

/**
 * 代码内容列
 */
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
        const lineNum = side === "left"
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

/**
 * Diff 视图容器（IDEA 风格 side-by-side）
 * 布局：代码内容 | 行号 [沟] 行号 | 代码内容
 * 纯滚动区域，标题栏由外部提供
 */
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

  // 滚动到指定行
  useEffect(() => {
    if (scrollToOriginal && containerRef.current) {
      const selector = `[data-original="${scrollToOriginal}"]`;
      const el = containerRef.current.querySelector(selector);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [scrollToOriginal]);

  // 同步滚动监听
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

  // 接收外部滚动同步
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
            {/* 左侧代码内容 */}
            <CodeContent lines={originalLines} side="left" />
            {/* 左侧行号（靠近中间） */}
            <LineNumbers lines={originalLines} side="left" maxWidth={lineNumberWidth} />
            {/* 中间沟 */}
            <DiffGutter originalLines={originalLines} modifiedLines={modifiedLines} />
            {/* 右侧行号（靠近中间） */}
            <LineNumbers lines={modifiedLines} side="right" maxWidth={lineNumberWidth} />
            {/* 右侧代码内容 */}
            <CodeContent lines={modifiedLines} side="right" />
          </div>
        )}
      </div>
  );
}

export function VersionCompareDrawer(props: VersionCompareDrawerProps) {
  const { open, sourceId, itemId, baseVersion, targetVersion, onClose } = props;

  const [loading, setLoading] = useState(false);
  const [compareResult, setCompareResult] = useState<VersionCompareResult | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [currentDiffIndex, setCurrentDiffIndex] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);

  // 同步滚动状态
  const scrollSyncRef = useRef<number>(0);

  const handleScrollSync = useCallback((scrollTop: number) => {
    scrollSyncRef.current = scrollTop;
  }, []);

  useEffect(() => {
    if (!open || !sourceId || !itemId) return;

    setLoading(true);
    setSelectedFilePath(null);
    setCurrentDiffIndex(0);
    setExpandedKeys([]);

    skillVersionApi
      .compareVersions(sourceId, itemId, baseVersion, targetVersion)
      .then((result) => {
        setCompareResult(result);
        const files = convertCompareResultToFiles(result);

        // 默认选择第一个变更文件（优先选择有变化的文件）
        const changedFiles = files.filter((f) => f.changeType !== "unchanged");
        if (changedFiles.length > 0) {
          setSelectedFilePath(changedFiles[0].path);
        } else if (files.length > 0) {
          setSelectedFilePath(files[0].path);
        }

        // 展开所有包含变更的文件夹
        const folderPaths = new Set<string>();
        files.forEach((file) => {
          if (file.changeType !== "unchanged") {
            const parts = file.path.split("/");
            for (let i = 1; i < parts.length; i++) {
              folderPaths.add(parts.slice(0, i).join("/"));
            }
          }
        });
        setExpandedKeys(Array.from(folderPaths));
      })
      .catch((err) => {
        console.error("Failed to compare versions:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [open, sourceId, itemId, baseVersion, targetVersion]);

  const files = useMemo(() => {
    if (!compareResult) return [];
    return convertCompareResultToFiles(compareResult);
  }, [compareResult]);

  const treeData = useMemo(() => {
    return buildFileTree(files);
  }, [files]);

  const selectedFile = useMemo(() => {
    if (!selectedFilePath) return null;
    return files.find((f) => f.path === selectedFilePath) || null;
  }, [files, selectedFilePath]);

  const diffData = useMemo(() => {
    if (!selectedFile) return null;
    return computeLineDiff(selectedFile.originalContent, selectedFile.modifiedContent);
  }, [selectedFile]);

  // 差异导航（按差异块为单位）
  const handleNavigateDiff = (direction: "next" | "prev") => {
    if (!diffData || diffData.diffBlocks.length === 0) return;
    const newIndex =
      direction === "next"
        ? (currentDiffIndex + 1) % diffData.diffBlocks.length
        : (currentDiffIndex - 1 + diffData.diffBlocks.length) % diffData.diffBlocks.length;
    setCurrentDiffIndex(newIndex);
  };

  // 文件导航（只导航变更文件）
  const handleNavigateFile = (direction: "next" | "prev") => {
    const changedFiles = files.filter((f) => f.changeType !== "unchanged");
    if (changedFiles.length <= 1 || !selectedFilePath) return;

    const currentIndex = changedFiles.findIndex((f) => f.path === selectedFilePath);
    if (currentIndex === -1) {
      // 当前选中的是未变更文件，切换到第一个变更文件
      setSelectedFilePath(changedFiles[0].path);
      setCurrentDiffIndex(0);
      return;
    }

    const newIndex =
      direction === "next"
        ? (currentIndex + 1) % changedFiles.length
        : (currentIndex - 1 + changedFiles.length) % changedFiles.length;

    setSelectedFilePath(changedFiles[newIndex].path);
    setCurrentDiffIndex(0);
  };

  // Tree 选择
  const handleTreeSelect: TreeProps["onSelect"] = (selectedKeys) => {
    if (selectedKeys.length === 0) return;
    const key = selectedKeys[0] as string;
    const file = files.find((f) => f.path === key);
    if (file) {
      setSelectedFilePath(file.path);
      setCurrentDiffIndex(0);
    }
  };

  // 自定义展开/折叠图标
  const switcherIcon = (props: { expanded?: boolean }) => (
    props.expanded
      ? <DownOutlined style={{ fontSize: 10, color: "#6e7781" }} />
      : <RightOutlined style={{ fontSize: 10, color: "#6e7781" }} />
  );

  // 当前差异块的滚动行号（跳转到差异块起始行）
  const currentBlock = diffData?.diffBlocks[currentDiffIndex];
  const scrollToOriginal = currentBlock?.startOriginal > 0 ? currentBlock.startOriginal : undefined;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={fullscreen ? "100%" : 1000}
      title={null}
      closable={false}
      styles={{
        body: { padding: 0, display: "flex", flexDirection: "column", height: "100%" },
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
            版本比对
          </Text>
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 8 }}>
            <Tag color="blue" style={{ borderRadius: 6 }}>{/^v/i.test(baseVersion) ? baseVersion : `v${baseVersion}`}</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>→</Text>
            <Tag color="green" style={{ borderRadius: 6 }}>{/^v/i.test(targetVersion) ? targetVersion : `v${targetVersion}`}</Tag>
          </div>
        </div>
        <Space size={8}>
          <Tooltip title={fullscreen ? "退出全屏" : "全屏显示"}>
            <Button
              onClick={() => setFullscreen(!fullscreen)}
              icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              type="text"
              style={{ color: "#6e7781" }}
            />
          </Tooltip>
          <Button onClick={onClose} icon={<CloseOutlined />} type="text" style={{ color: "#6e7781" }} />
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
            <PlusOutlined style={{ marginRight: 4 }} />
            +{compareResult.stats.added_lines}
          </Text>
          <Text style={{ fontSize: 13, color: "#cb2431" }}>
            <MinusOutlined style={{ marginRight: 4 }} />
            -{compareResult.stats.deleted_lines}
          </Text>
        </div>
      )}

      {/* 主体 */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>
        {loading ? (
          <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center" }}>
            <Spin size="large" />
          </div>
        ) : files.length === 0 ? (
          <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center" }}>
            <Empty description="无文件差异" />
          </div>
        ) : (
          <>
            {/* 左侧：文件树 */}
            <div
              style={{
                width: fullscreen ? 320 : 280,
                borderRight: "1px solid #e1e4e8",
                display: "flex",
                flexDirection: "column",
                backgroundColor: "#f6f8fa",
              }}
            >
              <div
                style={{
                  padding: "10px 16px",
                  borderBottom: "1px solid #e1e4e8",
                  backgroundColor: "#fff",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Text strong style={{ fontSize: 13, color: "#24292f" }}>
                  文件列表
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {files.length} 个文件
                </Text>
              </div>

              <div style={{ flex: 1, overflow: "auto", padding: "4px 0" }}>
                <Tree
                  showIcon
                  blockNode
                  expandedKeys={expandedKeys}
                  onExpand={(keys) => setExpandedKeys(keys as string[])}
                  selectedKeys={selectedFilePath ? [selectedFilePath] : []}
                  onSelect={handleTreeSelect}
                  treeData={treeData}
                  switcherIcon={switcherIcon}
                  style={{
                    backgroundColor: "transparent",
                    fontSize: 13,
                  }}
                  className="file-tree"
                />
                <style>{`
                  .file-tree .ant-tree-treenode {
                    display: flex !important;
                    align-items: center !important;
                    padding: 0 !important;
                    height: 32px !important;
                  }
                  .file-tree .ant-tree-switcher {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    width: 24px !important;
                    height: 32px !important;
                    flex-shrink: 0 !important;
                  }
                  .file-tree .ant-tree-iconEle {
                    display: flex !important;
                    align-items: center !important;
                    width: 20px !important;
                    height: 32px !important;
                    flex-shrink: 0 !important;
                  }
                  .file-tree .ant-tree-node-content-wrapper {
                    display: flex !important;
                    align-items: center !important;
                    flex: 1 !important;
                    min-height: 32px !important;
                    padding: 0 8px !important;
                    overflow: hidden !important;
                  }
                  .file-tree .ant-tree-title {
                    display: flex !important;
                    align-items: center !important;
                    flex: 1 !important;
                    overflow: hidden !important;
                    white-space: nowrap !important;
                    font-size: 13px !important;
                  }
                  .file-tree .ant-tree-node-selected {
                    background-color: #e8f4ff !important;
                  }
                  .file-tree .ant-tree-node-content-wrapper:hover {
                    background-color: #f3f4f6 !important;
                  }
                `}</style>
              </div>

              {/* 导航按钮 */}
              <div
                style={{
                  padding: "10px 16px",
                  borderTop: "1px solid #e1e4e8",
                  backgroundColor: "#fff",
                  display: "flex",
                  gap: 8,
                }}
              >
                <Button
                  size="small"
                  block
                  onClick={() => handleNavigateFile("prev")}
                  disabled={files.filter((f) => f.changeType !== "unchanged").length <= 1}
                >
                  <ArrowUpOutlined /> 上个变更
                </Button>
                <Button
                  size="small"
                  block
                  onClick={() => handleNavigateFile("next")}
                  disabled={files.filter((f) => f.changeType !== "unchanged").length <= 1}
                >
                  <ArrowDownOutlined /> 下个变更
                </Button>
              </div>
            </div>

            {/* 右侧：Diff 视图 */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
              {selectedFile ? (
                <>
                  {/* 文件标题栏 */}
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
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <FileOutlined style={{ color: getChangeColor(selectedFile.changeType), fontSize: 14 }} />
                      <Text strong style={{ fontSize: 13, color: "#24292f" }}>
                        {selectedFile.path}
                      </Text>
                      {selectedFile.changeType !== "unchanged" && (
                        <Tag
                          style={{
                            fontSize: 11,
                            borderRadius: 4,
                            backgroundColor:
                              selectedFile.changeType === "added"
                                ? "#dcffe4"
                                : selectedFile.changeType === "deleted"
                                  ? "#ffdce0"
                                  : "#fff5b1",
                            color: getChangeColor(selectedFile.changeType),
                            border: "none",
                          }}
                        >
                          {selectedFile.changeType === "added"
                            ? "新增"
                            : selectedFile.changeType === "deleted"
                              ? "删除"
                              : "修改"}
                        </Tag>
                      )}
                      {(selectedFile.addedLines > 0 || selectedFile.deletedLines > 0) && (
                        <Space size={4}>
                          {selectedFile.addedLines > 0 && (
                            <span style={{ fontSize: 11, color: "#28a745", fontWeight: 500 }}>
                              +{selectedFile.addedLines}
                            </span>
                          )}
                          {selectedFile.deletedLines > 0 && (
                            <span style={{ fontSize: 11, color: "#cb2431", fontWeight: 500 }}>
                              -{selectedFile.deletedLines}
                            </span>
                          )}
                        </Space>
                      )}
                    </div>

                    {/* 差异导航 */}
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

                  {/* IDEA 风格 side-by-side Diff */}
                  <DiffView
                    originalLines={diffData?.originalLines || []}
                    modifiedLines={diffData?.modifiedLines || []}
                    scrollToOriginal={scrollToOriginal}
                    onScroll={handleScrollSync}
                    scrollSyncRef={scrollSyncRef}
                  />
                </>
              ) : (
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    backgroundColor: "#f6f8fa",
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 14 }}>选择文件查看内容</Text>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </Drawer>
  );
}
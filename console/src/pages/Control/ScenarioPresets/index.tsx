import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Button,
  Dropdown,
  Empty,
  Input,
  Modal,
  Select,
  Spin,
  Switch,
  type MenuProps,
} from "antd";
import {
  AppstoreOutlined,
  DeleteOutlined,
  DownOutlined,
  FileTextOutlined,
  FolderOutlined,
  MoreOutlined,
  PlusOutlined,
  RightOutlined,
  SwapOutlined,
  UpOutlined,
} from "@ant-design/icons";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useIframeStore } from "@/stores/iframeStore";
import { marketApi } from "@/api/modules/market";
import { marketMcpApi } from "@/api/modules/marketMcp";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";
import type {
  ScenarioPresetBinding,
  ScenarioPresetNode,
  ScenarioPresetNodeKind,
} from "@/api/types/scenarioPreset";
import styles from "./index.module.less";

const NODE_LABEL: Record<ScenarioPresetNodeKind, string> = {
  domain: "能力域",
  capability: "能力",
  scenario: "场景",
};

type ScenarioPresetRow = {
  depth: number;
  hasChildren: boolean;
  node: ScenarioPresetNode;
};

function nextKind(kind: ScenarioPresetNodeKind): ScenarioPresetNodeKind | null {
  if (kind === "domain") return "capability";
  if (kind === "capability") return "scenario";
  return null;
}

function flattenVisibleNodes(
  nodes: ScenarioPresetNode[],
  expandedIds: Set<string>,
): ScenarioPresetRow[] {
  const children = groupNodesByParent(nodes);
  const rows: ScenarioPresetRow[] = [];

  const visit = (parentId: string | null, depth: number) => {
    const siblings = [...(children.get(parentId) ?? [])].sort(
      (left, right) => left.sort_order - right.sort_order,
    );
    siblings.forEach((node) => {
      const childNodes = children.get(node.id) ?? [];
      rows.push({ depth, hasChildren: childNodes.length > 0, node });
      if (childNodes.length > 0 && expandedIds.has(node.id)) {
        visit(node.id, depth + 1);
      }
    });
  };

  visit(null, 0);
  return rows;
}

function groupNodesByParent(nodes: ScenarioPresetNode[]) {
  const children = new Map<string | null, ScenarioPresetNode[]>();
  nodes.forEach((node) => {
    children.set(node.parent_id, [
      ...(children.get(node.parent_id) ?? []),
      node,
    ]);
  });
  return children;
}

function nodeIcon(kind: ScenarioPresetNodeKind) {
  if (kind === "domain") return <FolderOutlined />;
  if (kind === "capability") return <AppstoreOutlined />;
  return <FileTextOutlined />;
}

function nodePath(node: ScenarioPresetNode, nodes: ScenarioPresetNode[]) {
  const ancestors: string[] = [node.name];
  let parentId = node.parent_id;
  while (parentId) {
    const parent = nodes.find((item) => item.id === parentId);
    if (!parent) break;
    ancestors.unshift(parent.name);
    parentId = parent.parent_id;
  }
  return ancestors.join(" / ");
}

function mergeBindingOptions(
  bindings: ScenarioPresetBinding[],
  resourceType: ScenarioPresetBinding["resource_type"],
  options: { label: string; value: string }[],
) {
  const known = new Set(options.map((option) => option.value));
  return [
    ...options,
    ...bindings
      .filter(
        (binding) =>
          binding.resource_type === resourceType &&
          !known.has(binding.resource_id),
      )
      .map((binding) => ({
        label: `${binding.display_name}（当前不可用）`,
        value: binding.resource_id,
      })),
  ];
}

export default function ScenarioPresetsPage() {
  const { message } = useAppMessage();
  const sourceId = useIframeStore((state) => state.source) || "default";
  const [nodes, setNodes] = useState<ScenarioPresetNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ScenarioPresetNode | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [nodeName, setNodeName] = useState("");
  const [promptDraft, setPromptDraft] = useState("");
  const [active, setActive] = useState(true);
  const [bindings, setBindings] = useState<ScenarioPresetBinding[]>([]);
  const [bindingsLoaded, setBindingsLoaded] = useState(false);
  const [bindingsLoadFailed, setBindingsLoadFailed] = useState(false);
  const [skillOptions, setSkillOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [mcpOptions, setMcpOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const selectionRequestIdRef = useRef(0);
  const expansionInitializedRef = useRef(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await scenarioPresetApi.getAdminCatalog();
      setNodes(result.nodes);
      if (!expansionInitializedRef.current) {
        setExpandedIds(
          new Set(
            result.nodes
              .filter((node) => node.parent_id !== null)
              .map((node) => node.parent_id as string),
          ),
        );
        expansionInitializedRef.current = true;
      }
    } catch {
      message.error("场景预设目录加载失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const childrenByParent = useMemo(() => groupNodesByParent(nodes), [nodes]);
  const visibleRows = useMemo(
    () => flattenVisibleNodes(nodes, expandedIds),
    [expandedIds, nodes],
  );

  const loadNode = useCallback(
    async (node: ScenarioPresetNode) => {
      const requestId = selectionRequestIdRef.current + 1;
      selectionRequestIdRef.current = requestId;
      setSelected(node);
      setNodeName(node.name);
      setPromptDraft(node.prompt_draft);
      setActive(node.is_active);
      setBindings([]);
      setSkillOptions([]);
      setMcpOptions([]);
      setBindingsLoaded(node.kind !== "scenario");
      setBindingsLoadFailed(false);
      setDirty(false);
      if (node.kind !== "scenario") return;

      try {
        const bindingResult = await scenarioPresetApi.getBindings(node.id);
        if (selectionRequestIdRef.current !== requestId) return;
        setBindings(bindingResult.bindings);
        setBindingsLoaded(true);
        try {
          const [skills, mcps] = await Promise.all([
            marketApi.listMarketSkills(sourceId),
            marketMcpApi.listMarketMCP(undefined, undefined, sourceId),
          ]);
          if (selectionRequestIdRef.current !== requestId) return;
          setSkillOptions(
            mergeBindingOptions(
              bindingResult.bindings,
              "skill",
              skills.map((skill) => ({
                label: skill.chinese_name || skill.name,
                value: skill.item_id,
              })),
            ),
          );
          setMcpOptions(
            mergeBindingOptions(
              bindingResult.bindings,
              "mcp_service",
              mcps.map((mcp) => ({
                label: mcp.chinese_name || mcp.name,
                value: mcp.item_id,
              })),
            ),
          );
        } catch {
          if (selectionRequestIdRef.current !== requestId) return;
          setSkillOptions(
            mergeBindingOptions(bindingResult.bindings, "skill", []),
          );
          setMcpOptions(
            mergeBindingOptions(bindingResult.bindings, "mcp_service", []),
          );
          message.warning("市场资源暂不可加载，仍可保存或移除现有绑定");
        }
      } catch {
        if (selectionRequestIdRef.current !== requestId) return;
        setBindingsLoadFailed(true);
        message.error("场景关联资源加载失败，暂不能保存以避免覆盖现有绑定");
      }
    },
    [message, sourceId],
  );

  const createChild = useCallback(
    (parent: ScenarioPresetNode | null) => {
      const kind = parent ? nextKind(parent.kind) : "domain";
      if (!kind) return;
      Modal.confirm({
        title: `新建${NODE_LABEL[kind]}`,
        content: (
          <Input
            id="scenario-preset-node-name"
            placeholder={`${NODE_LABEL[kind]}名称`}
          />
        ),
        onOk: async () => {
          const input = document.getElementById(
            "scenario-preset-node-name",
          ) as HTMLInputElement | null;
          const name = input?.value.trim() || "";
          if (!name) throw new Error("名称不能为空");
          const created = await scenarioPresetApi.createNode({
            kind,
            parent_id: parent?.id ?? null,
            name,
          });
          await reload();
          await loadNode(created);
        },
      });
    },
    [loadNode, reload],
  );

  const saveSelected = useCallback(async (): Promise<boolean> => {
    if (!selected || !nodeName.trim()) return false;
    setSaving(true);
    try {
      const updated = await scenarioPresetApi.updateNode(selected.id, {
        name: nodeName.trim(),
        is_active: active,
        ...(selected.kind === "scenario" ? { prompt_draft: promptDraft } : {}),
      });
      if (
        selected.kind === "scenario" &&
        bindingsLoaded &&
        !bindingsLoadFailed
      ) {
        await scenarioPresetApi.replaceBindings(selected.id, bindings);
      }
      setSelected(updated);
      setDirty(false);
      message.success("场景预设已保存");
      await reload();
      return true;
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [
    active,
    bindings,
    bindingsLoadFailed,
    bindingsLoaded,
    message,
    nodeName,
    promptDraft,
    reload,
    selected,
  ]);

  const selectNode = useCallback(
    (node: ScenarioPresetNode) => {
      if (node.id === selected?.id) return;
      if (!dirty) {
        void loadNode(node);
        return;
      }
      Modal.confirm({
        title: "保存修改后再切换？",
        content: "当前节点有未保存的修改。",
        okText: "保存并切换",
        cancelText: "放弃修改",
        onOk: async () => {
          if (await saveSelected()) await loadNode(node);
        },
        onCancel: () => {
          setDirty(false);
          void loadNode(node);
        },
      });
    },
    [dirty, loadNode, saveSelected, selected],
  );

  const updateBindingIds = (
    type: ScenarioPresetBinding["resource_type"],
    ids: string[],
  ) => {
    const options = type === "skill" ? skillOptions : mcpOptions;
    const retained = bindings.filter(
      (binding) => binding.resource_type !== type,
    );
    setBindings([
      ...retained,
      ...ids.map((id, index) => ({
        resource_id: id,
        resource_type: type,
        display_name:
          options.find((option) => option.value === id)?.label || id,
        sort_order: index + 1,
      })),
    ]);
    setDirty(true);
  };

  const reorderNode = useCallback(
    async (node: ScenarioPresetNode, offset: number) => {
      const siblings = [...(childrenByParent.get(node.parent_id) ?? [])].sort(
        (left, right) => left.sort_order - right.sort_order,
      );
      const nextIndex =
        siblings.findIndex((item) => item.id === node.id) + offset;
      if (nextIndex < 0 || nextIndex >= siblings.length) return;
      await scenarioPresetApi.reorderNode(node.id, nextIndex + 1);
      await reload();
    },
    [childrenByParent, reload],
  );

  const moveNode = useCallback(
    (node: ScenarioPresetNode) => {
      if (node.kind === "domain") return;
      const parentKind = node.kind === "capability" ? "domain" : "capability";
      const destinations = nodes.filter(
        (item) => item.kind === parentKind && item.id !== node.parent_id,
      );
      if (!destinations.length) {
        message.info(`暂无可移动到的${NODE_LABEL[parentKind]}`);
        return;
      }
      let parentId = destinations[0].id;
      Modal.confirm({
        title: `移动${NODE_LABEL[node.kind]}`,
        content: (
          <Select
            aria-label="目标父级"
            defaultValue={parentId}
            options={destinations.map((item) => ({
              label: item.name,
              value: item.id,
            }))}
            onChange={(value) => {
              parentId = value;
            }}
            style={{ width: "100%" }}
          />
        ),
        onOk: async () => {
          await scenarioPresetApi.moveNode(node.id, parentId);
          setDirty(false);
          await reload();
        },
      });
    },
    [message, nodes, reload],
  );

  const deleteNode = useCallback(
    (node: ScenarioPresetNode) => {
      const hasChildren = (childrenByParent.get(node.id)?.length ?? 0) > 0;
      if (hasChildren) {
        message.info("该节点有子节点，请先移动或删除子节点后再删除。");
        return;
      }
      Modal.confirm({
        title: "确认删除",
        content: `删除“${node.name}”后不可恢复。`,
        okType: "danger",
        onOk: async () => {
          await scenarioPresetApi.deleteNode(node.id);
          if (selected?.id === node.id) {
            setSelected(null);
            setDirty(false);
          }
          await reload();
        },
      });
    },
    [childrenByParent, message, reload, selected],
  );

  const toggleExpanded = (nodeId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  if (loading) return <Spin />;
  if (!nodes.length) {
    return (
      <Empty description="暂未配置能力域、能力和场景">
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => createChild(null)}
        >
          新建能力域
        </Button>
      </Empty>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>场景预设管理</h1>
          <p>按能力域、能力、场景维护新会话入口。</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => createChild(null)}
        >
          新建能力域
        </Button>
      </header>

      <div className={styles.workspace}>
        <section className={styles.catalogPanel} aria-label="场景目录">
          <div className={styles.catalogMeta}>共 {nodes.length} 个节点</div>
          <div className={styles.table} role="table" aria-label="场景预设目录">
            <div className={styles.tableHeader} role="row">
              <span>名称</span>
              <span>描述</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            {visibleRows.map(({ depth, hasChildren, node }) => {
              const siblingNodes = [
                ...(childrenByParent.get(node.parent_id) ?? []),
              ].sort((left, right) => left.sort_order - right.sort_order);
              const siblingIndex = siblingNodes.findIndex(
                (item) => item.id === node.id,
              );
              const childKind = nextKind(node.kind);
              const menuItems: MenuProps["items"] = [
                ...(node.kind !== "domain"
                  ? [
                      {
                        key: "move",
                        icon: <SwapOutlined />,
                        label: "移动",
                      },
                    ]
                  : []),
                {
                  key: "delete",
                  danger: true,
                  icon: <DeleteOutlined />,
                  label: "删除",
                },
              ];
              const description =
                node.kind === "scenario"
                  ? node.prompt_draft || "未填写提示草稿"
                  : `${childrenByParent.get(node.id)?.length ?? 0} 个${
                      node.kind === "domain" ? "能力" : "场景"
                    }`;

              return (
                <div
                  key={node.id}
                  aria-selected={selected?.id === node.id}
                  className={`${styles.row} ${
                    selected?.id === node.id ? styles.rowSelected : ""
                  }`}
                  role="row"
                  tabIndex={0}
                  onClick={() => selectNode(node)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectNode(node);
                    }
                  }}
                >
                  <div
                    className={styles.rowName}
                    style={{ "--row-depth": depth } as CSSProperties}
                  >
                    {hasChildren ? (
                      <Button
                        aria-label={`${
                          expandedIds.has(node.id) ? "收起" : "展开"
                        }${node.name}`}
                        className={styles.expandButton}
                        icon={
                          expandedIds.has(node.id) ? (
                            <DownOutlined />
                          ) : (
                            <RightOutlined />
                          )
                        }
                        size="small"
                        type="text"
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleExpanded(node.id);
                        }}
                      />
                    ) : (
                      <span className={styles.expandPlaceholder} />
                    )}
                    <span className={styles.nodeIcon}>
                      {nodeIcon(node.kind)}
                    </span>
                    <span className={styles.nodeName}>{node.name}</span>
                  </div>
                  <span className={styles.description} title={description}>
                    {description}
                  </span>
                  <span
                    className={
                      node.is_active
                        ? styles.statusActive
                        : styles.statusInactive
                    }
                  >
                    {node.is_active ? "启用" : "已停用"}
                  </span>
                  <div className={styles.rowActions}>
                    {childKind && (
                      <Button
                        size="small"
                        type="link"
                        icon={<PlusOutlined />}
                        onClick={(event) => {
                          event.stopPropagation();
                          createChild(node);
                        }}
                      >
                        新建{NODE_LABEL[childKind]}
                      </Button>
                    )}
                    <Button
                      aria-label={`上移${node.name}`}
                      disabled={siblingIndex <= 0}
                      icon={<UpOutlined />}
                      size="small"
                      type="text"
                      onClick={(event) => {
                        event.stopPropagation();
                        void reorderNode(node, -1);
                      }}
                    />
                    <Button
                      aria-label={`下移${node.name}`}
                      disabled={siblingIndex >= siblingNodes.length - 1}
                      icon={<DownOutlined />}
                      size="small"
                      type="text"
                      onClick={(event) => {
                        event.stopPropagation();
                        void reorderNode(node, 1);
                      }}
                    />
                    <Dropdown
                      menu={{
                        items: menuItems,
                        onClick: ({ domEvent, key }) => {
                          domEvent.stopPropagation();
                          if (key === "move") moveNode(node);
                          if (key === "delete") deleteNode(node);
                        },
                      }}
                    >
                      <Button
                        aria-label={`${node.name}更多操作`}
                        icon={<MoreOutlined />}
                        size="small"
                        type="text"
                        onClick={(event) => event.stopPropagation()}
                      />
                    </Dropdown>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <aside className={styles.detailsPanel} aria-label="节点详情">
          {!selected ? (
            <Empty
              className={styles.detailsEmpty}
              description="选择左侧节点开始编辑"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <>
              <div className={styles.detailsHeader}>
                <span>{NODE_LABEL[selected.kind]}设置</span>
                <span>{nodePath(selected, nodes)}</span>
              </div>
              <h2>{selected.name}</h2>
              <div className={styles.detailsBody}>
                <label htmlFor="scenario-preset-name">名称</label>
                <Input
                  id="scenario-preset-name"
                  aria-label="名称"
                  value={nodeName}
                  onChange={(event) => {
                    setNodeName(event.target.value);
                    setDirty(true);
                  }}
                />

                {selected.kind === "scenario" && (
                  <>
                    <label htmlFor="scenario-preset-prompt">提示草稿</label>
                    <Input.TextArea
                      id="scenario-preset-prompt"
                      aria-label="提示草稿"
                      autoSize={{ minRows: 5 }}
                      value={promptDraft}
                      onChange={(event) => {
                        setPromptDraft(event.target.value);
                        setDirty(true);
                      }}
                    />
                    <label htmlFor="scenario-preset-skills">关联 Skill</label>
                    <Select
                      id="scenario-preset-skills"
                      aria-label="关联 Skill"
                      mode="multiple"
                      options={skillOptions}
                      value={bindings
                        .filter((binding) => binding.resource_type === "skill")
                        .map((binding) => binding.resource_id)}
                      onChange={(values) => updateBindingIds("skill", values)}
                    />
                    <label htmlFor="scenario-preset-mcps">关联 MCP 服务</label>
                    <Select
                      id="scenario-preset-mcps"
                      aria-label="关联 MCP 服务"
                      mode="multiple"
                      options={mcpOptions}
                      value={bindings
                        .filter(
                          (binding) => binding.resource_type === "mcp_service",
                        )
                        .map((binding) => binding.resource_id)}
                      onChange={(values) =>
                        updateBindingIds("mcp_service", values)
                      }
                    />
                    <p className={styles.bindingHelp}>
                      资源仅记录市场稳定 ID；首次发送消息时才校验并解析。
                    </p>
                  </>
                )}

                <div className={styles.switchRow}>
                  <span>启用</span>
                  <Switch
                    aria-label="启用状态"
                    checked={active}
                    onChange={(value) => {
                      setActive(value);
                      setDirty(true);
                    }}
                  />
                </div>
                {(childrenByParent.get(selected.id)?.length ?? 0) > 0 && (
                  <p className={styles.childrenHint}>
                    该节点有子节点，仅支持编辑或停用；请先移动或删除子节点后再删除。
                  </p>
                )}
              </div>
              <div className={styles.detailsFooter}>
                <Button
                  type="primary"
                  loading={saving}
                  disabled={
                    !nodeName.trim() ||
                    (selected.kind === "scenario" &&
                      (!bindingsLoaded || bindingsLoadFailed))
                  }
                  onClick={() => void saveSelected()}
                >
                  保存更改
                </Button>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

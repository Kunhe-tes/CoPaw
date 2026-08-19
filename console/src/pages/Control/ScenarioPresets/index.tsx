import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Tree,
  Typography,
  type TreeDataNode,
} from "antd";
import {
  DeleteOutlined,
  DownOutlined,
  PlusOutlined,
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

const NODE_LABEL: Record<ScenarioPresetNodeKind, string> = {
  domain: "能力域",
  capability: "能力",
  scenario: "场景",
};

function nextKind(kind: ScenarioPresetNodeKind): ScenarioPresetNodeKind | null {
  if (kind === "domain") return "capability";
  if (kind === "capability") return "scenario";
  return null;
}

function toTreeData(nodes: ScenarioPresetNode[]): TreeDataNode[] {
  const children = new Map<string | null, ScenarioPresetNode[]>();
  nodes.forEach((node) => {
    const siblingNodes = children.get(node.parent_id) ?? [];
    siblingNodes.push(node);
    children.set(node.parent_id, siblingNodes);
  });
  const renderNode = (node: ScenarioPresetNode): TreeDataNode => ({
    key: node.id,
    title: (
      <Space size={8}>
        <span>{node.name}</span>
        {!node.is_active && (
          <Typography.Text type="secondary">已停用</Typography.Text>
        )}
      </Space>
    ),
    children: (children.get(node.id) ?? [])
      .sort((left, right) => left.sort_order - right.sort_order)
      .map(renderNode),
  });
  return (children.get(null) ?? [])
    .sort((left, right) => left.sort_order - right.sort_order)
    .map(renderNode);
}

export default function ScenarioPresetsPage() {
  const { message } = useAppMessage();
  const sourceId = useIframeStore((state) => state.source) || "default";
  const [nodes, setNodes] = useState<ScenarioPresetNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ScenarioPresetNode | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [nodeName, setNodeName] = useState("");
  const [promptDraft, setPromptDraft] = useState("");
  const [active, setActive] = useState(true);
  const [bindings, setBindings] = useState<ScenarioPresetBinding[]>([]);
  const [skillOptions, setSkillOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [mcpOptions, setMcpOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const drawerRequestIdRef = useRef(0);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await scenarioPresetApi.getAdminCatalog();
      setNodes(result.nodes);
    } catch {
      message.error("场景预设目录加载失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const treeData = useMemo(() => toTreeData(nodes), [nodes]);
  const childrenByParent = useMemo(() => {
    const result = new Map<string, ScenarioPresetNode[]>();
    nodes.forEach((node) => {
      if (!node.parent_id) return;
      result.set(node.parent_id, [...(result.get(node.parent_id) ?? []), node]);
    });
    return result;
  }, [nodes]);

  const openDrawer = useCallback(
    async (node: ScenarioPresetNode) => {
      const requestId = drawerRequestIdRef.current + 1;
      drawerRequestIdRef.current = requestId;
      setSelected(node);
      setNodeName(node.name);
      setPromptDraft(node.prompt_draft);
      setActive(node.is_active);
      setBindings([]);
      setDrawerOpen(true);
      if (node.kind !== "scenario") return;
      try {
        const [bindingResult, skills, mcps] = await Promise.all([
          scenarioPresetApi.getBindings(node.id),
          marketApi.listMarketSkills(sourceId),
          marketMcpApi.listMarketMCP(undefined, undefined, sourceId),
        ]);
        if (drawerRequestIdRef.current !== requestId) return;
        setBindings(bindingResult.bindings);
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
        if (drawerRequestIdRef.current !== requestId) return;
        message.warning("部分市场资源暂不可加载，可继续编辑场景文本");
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
          await scenarioPresetApi.createNode({
            kind,
            parent_id: parent?.id ?? null,
            name,
          });
          await reload();
        },
      });
    },
    [reload],
  );

  const saveDrawer = useCallback(async () => {
    if (!selected || !nodeName.trim()) return;
    try {
      await scenarioPresetApi.updateNode(selected.id, {
        name: nodeName.trim(),
        is_active: active,
        ...(selected.kind === "scenario" ? { prompt_draft: promptDraft } : {}),
      });
      if (selected.kind === "scenario")
        await scenarioPresetApi.replaceBindings(selected.id, bindings);
      message.success("场景预设已保存");
      setDrawerOpen(false);
      await reload();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存失败");
    }
  }, [active, bindings, message, nodeName, promptDraft, reload, selected]);

  const deleteSelected = useCallback(() => {
    if (!selected) return;
    Modal.confirm({
      title: "确认删除",
      content: `删除“${selected.name}”后不可恢复。只有没有子节点的条目可以删除。`,
      okType: "danger",
      onOk: async () => {
        await scenarioPresetApi.deleteNode(selected.id);
        setDrawerOpen(false);
        await reload();
      },
    });
  }, [reload, selected]);

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
  };

  const reorderNode = useCallback(
    async (node: ScenarioPresetNode, offset: number) => {
      const siblings = nodes
        .filter((item) => item.parent_id === node.parent_id)
        .sort((left, right) => left.sort_order - right.sort_order);
      const nextIndex =
        siblings.findIndex((item) => item.id === node.id) + offset;
      if (nextIndex < 0 || nextIndex >= siblings.length) return;
      await scenarioPresetApi.reorderNode(node.id, nextIndex + 1);
      await reload();
    },
    [nodes, reload],
  );

  const moveSelected = useCallback(() => {
    if (!selected || selected.kind === "domain") return;
    const parentKind = selected.kind === "capability" ? "domain" : "capability";
    const destinations = nodes.filter(
      (node) => node.kind === parentKind && node.id !== selected.parent_id,
    );
    if (!destinations.length) {
      message.info(`暂无可移动到的${NODE_LABEL[parentKind]}`);
      return;
    }
    let parentId = destinations[0].id;
    Modal.confirm({
      title: `移动${NODE_LABEL[selected.kind]}`,
      content: (
        <Select
          aria-label="目标父级"
          defaultValue={parentId}
          options={destinations.map((node) => ({
            label: node.name,
            value: node.id,
          }))}
          onChange={(value) => {
            parentId = value;
          }}
          style={{ width: "100%" }}
        />
      ),
      onOk: async () => {
        await scenarioPresetApi.moveNode(selected.id, parentId);
        setDrawerOpen(false);
        await reload();
      },
    });
  }, [message, nodes, reload, selected]);

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
    <div style={{ maxWidth: 980 }}>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Space style={{ justifyContent: "space-between", width: "100%" }}>
          <div>
            <Typography.Title level={3}>场景预设管理</Typography.Title>
            <Typography.Text type="secondary">
              按能力域、能力、场景维护新会话入口。
            </Typography.Text>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => createChild(null)}
          >
            新建能力域
          </Button>
        </Space>
        <Tree
          blockNode
          defaultExpandAll
          treeData={treeData}
          onSelect={(keys) => {
            const node = nodes.find((item) => item.id === keys[0]);
            if (node) void openDrawer(node);
          }}
          titleRender={(data) => {
            const node = nodes.find((item) => item.id === data.key);
            if (!node) return null;
            const childKind = nextKind(node.kind);
            const siblings = nodes
              .filter((item) => item.parent_id === node.parent_id)
              .sort((left, right) => left.sort_order - right.sort_order);
            const index = siblings.findIndex((item) => item.id === node.id);
            return (
              <Space style={{ justifyContent: "space-between", width: "100%" }}>
                {node.name}
                <Space size={2}>
                  <Button
                    aria-label={`上移${node.name}`}
                    disabled={index <= 0}
                    size="small"
                    type="text"
                    icon={<UpOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      void reorderNode(node, -1);
                    }}
                  />
                  <Button
                    aria-label={`下移${node.name}`}
                    disabled={index >= siblings.length - 1}
                    size="small"
                    type="text"
                    icon={<DownOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      void reorderNode(node, 1);
                    }}
                  />
                  {childKind && (
                    <Button
                      size="small"
                      type="text"
                      icon={<PlusOutlined />}
                      onClick={(event) => {
                        event.stopPropagation();
                        createChild(node);
                      }}
                    >
                      新建{NODE_LABEL[childKind]}
                    </Button>
                  )}
                </Space>
              </Space>
            );
          }}
        />
      </Space>
      <Drawer
        title={selected ? `${NODE_LABEL[selected.kind]}设置` : "设置"}
        open={drawerOpen}
        width={520}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Space>
            {selected?.kind !== "domain" && (
              <Button icon={<SwapOutlined />} onClick={moveSelected}>
                移动
              </Button>
            )}
            <Button danger icon={<DeleteOutlined />} onClick={deleteSelected}>
              删除
            </Button>
            <Button type="primary" onClick={() => void saveDrawer()}>
              保存
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <label>
            名称
            <Input
              value={nodeName}
              onChange={(event) => setNodeName(event.target.value)}
            />
          </label>
          <Space>
            <span>启用</span>
            <Switch checked={active} onChange={setActive} />
          </Space>
          {selected?.kind === "scenario" && (
            <>
              <label>
                提示草稿
                <Input.TextArea
                  value={promptDraft}
                  onChange={(event) => setPromptDraft(event.target.value)}
                  autoSize={{ minRows: 5 }}
                />
              </label>
              <label>
                关联 Skill
                <Select
                  mode="multiple"
                  style={{ width: "100%" }}
                  options={skillOptions}
                  value={bindings
                    .filter((binding) => binding.resource_type === "skill")
                    .map((binding) => binding.resource_id)}
                  onChange={(values) => updateBindingIds("skill", values)}
                />
              </label>
              <label>
                关联 MCP 服务
                <Select
                  mode="multiple"
                  style={{ width: "100%" }}
                  options={mcpOptions}
                  value={bindings
                    .filter(
                      (binding) => binding.resource_type === "mcp_service",
                    )
                    .map((binding) => binding.resource_id)}
                  onChange={(values) => updateBindingIds("mcp_service", values)}
                />
              </label>
              <Typography.Text type="secondary">
                资源仅记录市场稳定 ID；首次发送消息时才校验并解析。
              </Typography.Text>
            </>
          )}
          {selected && (childrenByParent.get(selected.id)?.length ?? 0) > 0 && (
            <Typography.Text type="secondary">
              该节点有子节点，仅支持编辑或停用；请先移动或删除子节点后再删除。
            </Typography.Text>
          )}
        </Space>
      </Drawer>
    </div>
  );
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

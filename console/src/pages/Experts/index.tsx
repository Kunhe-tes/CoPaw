import { useEffect, useState } from "react";
import { Button, Drawer, Empty, Form, Input, Popconfirm, Space, Spin, Switch, Table, Tag, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { expertsApi, type Expert, type ExpertPayload } from "../../api/modules/experts";
import { useAppMessage } from "../../hooks/useAppMessage";

const emptyPayload: ExpertPayload = {
  name: "", description: "", instruction: "", trigger_keywords: [], skills: [],
  mcps: null, tools: {}, model: null, budget: {},
};

const splitList = (value?: string) => value?.split(",").map((item) => item.trim()).filter(Boolean) || [];

export default function ExpertsPage() {
  const [items, setItems] = useState<Expert[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<Expert | null>(null);
  const [form] = Form.useForm<ExpertPayload & { keywordsText?: string; skillsText?: string; mcpsText?: string }>();
  const { message } = useAppMessage();
  const load = async () => { setLoading(true); try { setItems(await expertsApi.listExperts()); } catch (error) { message.error(error instanceof Error ? error.message : "加载专家失败"); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  const open = (expert?: Expert) => { setSelected(expert || null); setDrawerOpen(true); form.setFieldsValue(expert ? { ...expert.definition as ExpertPayload, keywordsText: ((expert.definition?.trigger_keywords as string[]) || []).join(", "), skillsText: ((expert.definition?.agent_owned?.declared_skills as string[]) || []).join(", "), mcpsText: ((expert.definition?.agent_owned?.declared_mcps as string[]) || []).join(", ") } : emptyPayload); };
  const save = async () => { const values = await form.validateFields(); const payload: ExpertPayload = { name: values.name, description: values.description, instruction: values.instruction, trigger_keywords: splitList(values.keywordsText), skills: splitList(values.skillsText), mcps: values.mcpsText?.trim() ? splitList(values.mcpsText) : null, tools: {}, model: null, budget: {} }; setSaving(true); try { const saved = selected ? await expertsApi.updateExpert(selected.definition_id, payload, selected.revision) : await expertsApi.createExpert(payload); setSelected(saved); message.success("专家配置已保存；启停将在下一轮主 Agent 生效"); await load(); } catch (error) { message.error(error instanceof Error ? error.message : "保存失败"); } finally { setSaving(false); } };
  const toggle = async (expert: Expert, enabled: boolean) => { try { await (enabled ? expertsApi.enableExpert(expert.definition_id, expert.revision) : expertsApi.disableExpert(expert.definition_id, expert.revision)); await load(); } catch (error) { message.error(error instanceof Error ? error.message : "状态更新失败"); } };
  return <section style={{ padding: 24 }}><Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }}><div><Typography.Title level={3} style={{ margin: 0 }}>专家</Typography.Title><Typography.Text type="secondary">配置当前 Agent 的可复用子代理专家；仅启用配置会在下一轮生效。</Typography.Text></div><Button type="primary" icon={<PlusOutlined />} onClick={() => open()}>新建专家</Button></Space><Spin spinning={loading}>{items.length ? <Table rowKey="definition_id" pagination={false} dataSource={items} columns={[{ title: "名称", render: (_, item) => item.definition?.name || item.definition_id }, { title: "说明", render: (_, item) => item.definition?.description || item.validation_error }, { title: "关键词", render: (_, item) => ((item.definition?.trigger_keywords as string[]) || []).map((word) => <Tag key={word}>{word}</Tag>) }, { title: "状态", render: (_, item) => item.valid ? <Switch checked={item.enabled} onChange={(checked) => void toggle(item, checked)} /> : <Tag color="error">配置无效</Tag> }, { title: "操作", render: (_, item) => <Space><Button type="link" disabled={!item.valid} onClick={() => open(item)}>编辑</Button><Popconfirm title="删除此专家？" onConfirm={() => void expertsApi.deleteExpert(item.definition_id, item.revision).then(load)}><Button type="link" danger>删除</Button></Popconfirm></Space> }]} /> : <Empty description="还没有自定义专家" />}</Spin><Drawer title={selected ? "编辑专家" : "新建专家"} width={560} open={drawerOpen} onClose={() => { setDrawerOpen(false); setSelected(null); form.resetFields(); }} extra={<Button type="primary" loading={saving} onClick={() => void save()}>保存</Button>}><Form layout="vertical" form={form}><Form.Item name="name" label="调用名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="instruction" label="专家指令" rules={[{ required: true }]}><Input.TextArea rows={8} /></Form.Item><Form.Item name="keywordsText" label="关键词"><Input placeholder="用逗号分隔" /></Form.Item><Form.Item name="skillsText" label="Skills"><Input placeholder="可选，用逗号分隔" /></Form.Item><Form.Item name="mcpsText" label="MCP"><Input placeholder="留空将继承主 Agent 已启用 MCP" /></Form.Item></Form></Drawer></section>;
}

import {
  Button,
  Checkbox,
  Collapse,
  Empty,
  Input,
  Modal,
  Select,
  Skeleton,
  Switch,
  Table,
  Tabs,
  Tag,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  hookManagementApi,
  type HookScript,
} from "@/api/modules/hookManagement";
import { useAppMessage } from "@/hooks/useAppMessage";

import {
  addHandler,
  addEvent,
  addGroup,
  defaultContext,
  removeGroup,
  removeHandler,
} from "./draft";
import type {
  HookConfigDraft,
  HookEventName,
  HookHandlerDraft,
  HookHandlerType,
  HookTreeSelection,
} from "./types";
import styles from "./index.module.less";

const events: HookEventName[] = [
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "PostToolUseFailure",
  "BeforeStop",
  "Stop",
];

const promptEvents = new Set(events);

function findHandler(
  config: HookConfigDraft,
  selected: HookTreeSelection,
): HookHandlerDraft | null {
  if (selected.kind !== "handler") return null;
  return (
    config.events[selected.event]
      ?.find((group) => group.id === selected.groupId)
      ?.hooks.find((handler) => handler.id === selected.handlerId) ?? null
  );
}

function updateHandler(
  config: HookConfigDraft,
  selected: HookTreeSelection,
  changes: Partial<HookHandlerDraft>,
): HookConfigDraft {
  if (selected.kind !== "handler") return config;
  return {
    ...config,
    events: {
      ...config.events,
      [selected.event]: config.events[selected.event]?.map((group) =>
        group.id !== selected.groupId
          ? group
          : {
              ...group,
              hooks: group.hooks.map((handler) =>
                handler.id === selected.handlerId
                  ? { ...handler, ...changes }
                  : handler,
              ),
            },
      ),
    },
  };
}

function HookManagementPage() {
  const { message } = useAppMessage();
  const [draft, setDraft] = useState<HookConfigDraft | null>(null);
  const [revision, setRevision] = useState("");
  const [scripts, setScripts] = useState<HookScript[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HookTreeSelection>({ kind: "root" });
  const [testOpen, setTestOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(
    null,
  );
  const [conflictOpen, setConflictOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [overwriteOpen, setOverwriteOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    accepted: string[];
    warned: string[];
    failed: Array<{ filename: string; reason: string }>;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [snapshot, files] = await Promise.all([
        hookManagementApi.getConfiguration(),
        hookManagementApi.listScripts(),
      ]);
      setDraft(snapshot.hooks as HookConfigDraft);
      setRevision(snapshot.revision);
      setScripts(files);
      setSelected({ kind: "root" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载 Hook 配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handler = useMemo(
    () => (draft ? findHandler(draft, selected) : null),
    [draft, selected],
  );

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const snapshot = await hookManagementApi.saveConfiguration(
        draft,
        revision,
      );
      setDraft(snapshot.hooks as HookConfigDraft);
      setRevision(snapshot.revision);
      message.success("Hook 配置已保存，Default Agent 将异步加载新配置");
    } catch (cause) {
      if ((cause as { status?: number }).status === 409) {
        setConflictOpen(true);
      } else {
        message.error(
          cause instanceof Error ? cause.message : "保存 Hook 配置失败",
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const upload = async (overwrite: string[]) => {
    if (!pendingFiles.length) return;
    setUploading(true);
    try {
      const result = await hookManagementApi.uploadScripts(
        pendingFiles,
        overwrite,
      );
      setUploadResult(result);
      setScripts(await hookManagementApi.listScripts());
      setPendingFiles([]);
      setOverwriteOpen(false);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "上传脚本失败");
    } finally {
      setUploading(false);
    }
  };

  const onFiles = (files: FileList | null) => {
    const next = Array.from(files ?? []);
    setPendingFiles(next);
    const duplicate = next.some((file) =>
      scripts.some((script) => script.filename === file.name),
    );
    if (duplicate) setOverwriteOpen(true);
    else void upload([]);
  };

  const runTest = async () => {
    if (!handler || selected.kind !== "handler") return;
    setTesting(true);
    try {
      const result = await hookManagementApi.manualTest(
        handler,
        defaultContext(selected.event),
      );
      setTestResult(result.redacted_summary);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "人工测试失败");
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <Skeleton active paragraph={{ rows: 12 }} />
      </div>
    );
  }
  if (error || !draft) {
    return (
      <div className={styles.page}>
        <Empty description={error ?? "未找到 Default Agent Profile"}>
          <Button onClick={() => void load()}>重试</Button>
        </Empty>
      </div>
    );
  }

  const renderHandlerEditor = () => {
    if (!handler || selected.kind !== "handler") return null;
    const argv = Array.isArray(handler.argv) ? handler.argv.map(String) : [];
    return (
      <div className={styles.editor}>
        <div className={styles.editorHeader}>
          <div>
            <h2>{handler.id || "未命名 Handler"}</h2>
            <span>{handler.type} Handler</span>
          </div>
          <Button onClick={() => setTestOpen(true)}>执行人工测试</Button>
        </div>
        <label>
          Handler ID
          <Input
            value={handler.id}
            onChange={(event) =>
              setDraft(
                updateHandler(draft, selected, { id: event.target.value }),
              )
            }
          />
        </label>
        {handler.type === "command" && (
          <>
            <div className={styles.sectionTitle}>命令参数（按顺序传递）</div>
            {argv.map((value, index) => (
              <label key={index}>
                {`命令参数 ${index + 1}`}
                <Input
                  value={value}
                  onChange={(event) => {
                    const next = [...argv];
                    next[index] = event.target.value;
                    setDraft(updateHandler(draft, selected, { argv: next }));
                  }}
                />
              </label>
            ))}
            <Button
              type="dashed"
              onClick={() =>
                setDraft(
                  updateHandler(draft, selected, { argv: [...argv, ""] }),
                )
              }
            >
              添加参数
            </Button>
            <label>
              工作目录
              <Input
                value={String(handler.cwd ?? "")}
                onChange={(event) =>
                  setDraft(
                    updateHandler(draft, selected, { cwd: event.target.value }),
                  )
                }
              />
            </label>
          </>
        )}
        {handler.type === "http" && (
          <label>
            请求地址
            <Input
              value={String(handler.url ?? "")}
              onChange={(event) =>
                setDraft(
                  updateHandler(draft, selected, { url: event.target.value }),
                )
              }
            />
          </label>
        )}
        {handler.type === "prompt" && (
          <label>
            Prompt
            <Input.TextArea
              value={String(handler.prompt ?? "")}
              onChange={(event) =>
                setDraft(
                  updateHandler(draft, selected, {
                    prompt: event.target.value,
                  }),
                )
              }
              rows={5}
            />
          </label>
        )}
        <Collapse
          items={[
            {
              key: "advanced",
              label: "高级设置",
              children: (
                <div className={styles.advanced}>
                  <label>
                    条件表达式
                    <Input
                      value={String(handler.if ?? "")}
                      onChange={(event) =>
                        setDraft(
                          updateHandler(draft, selected, {
                            if: event.target.value,
                          }),
                        )
                      }
                    />
                  </label>
                  <label>
                    超时（秒）
                    <Input
                      type="number"
                      value={String(handler.timeout ?? 10)}
                      onChange={(event) =>
                        setDraft(
                          updateHandler(draft, selected, {
                            timeout: Number(event.target.value),
                          }),
                        )
                      }
                    />
                  </label>
                  <label>
                    失败策略
                    <Select
                      value={String(handler.failPolicy ?? "allow")}
                      options={[
                        { value: "allow", label: "允许" },
                        { value: "block", label: "阻断" },
                      ]}
                      onChange={(value) =>
                        setDraft(
                          updateHandler(draft, selected, { failPolicy: value }),
                        )
                      }
                    />
                  </label>
                </div>
              ),
            },
          ]}
        />
      </div>
    );
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>
            Hook 管理 <Tag>Default Agent · 当前租户</Tag>
          </h1>
          <p>配置草稿保存后才会激活；脚本上传立即保存到受控脚本库。</p>
        </div>
        <Button type="primary" loading={saving} onClick={() => void save()}>
          保存并激活
        </Button>
      </header>
      <Tabs
        items={[
          {
            key: "configuration",
            label: "配置",
            children: (
              <div className={styles.workspace}>
                <aside className={styles.tree}>
                  <div className={styles.treeTop}>
                    <strong>事件与处理链</strong>
                    <Select
                      size="small"
                      placeholder="添加事件"
                      options={events
                        .filter((event) => !draft.events[event])
                        .map((event) => ({ value: event, label: event }))}
                      onChange={(event: HookEventName) =>
                        setDraft(addEvent(draft, event))
                      }
                    />
                  </div>
                  <Button
                    className={selected.kind === "root" ? styles.selected : ""}
                    type="text"
                    onClick={() => setSelected({ kind: "root" })}
                  >
                    全局开关
                  </Button>
                  {Object.entries(draft.events).map(([event, groups]) => (
                    <div key={event}>
                      <div className={styles.event}>
                        {event}
                        <Button
                          size="small"
                          type="link"
                          onClick={() =>
                            setDraft(addGroup(draft, event as HookEventName))
                          }
                        >
                          添加组
                        </Button>
                      </div>
                      {groups?.map((group) => (
                        <div key={group.id} className={styles.group}>
                          <div>
                            <Button
                              className={
                                selected.kind === "group" &&
                                selected.groupId === group.id
                                  ? styles.selected
                                  : ""
                              }
                              type="text"
                              onClick={() =>
                                setSelected({
                                  kind: "group",
                                  event: event as HookEventName,
                                  groupId: group.id,
                                })
                              }
                            >
                              {group.id}
                            </Button>
                            <Button
                              danger
                              type="text"
                              size="small"
                              onClick={() =>
                                setDraft(
                                  removeGroup(
                                    draft,
                                    event as HookEventName,
                                    group.id,
                                  ),
                                )
                              }
                            >
                              删除
                            </Button>
                          </div>
                          {group.hooks.map((item) => (
                            <div key={item.id} className={styles.handler}>
                              <Button
                                className={
                                  selected.kind === "handler" &&
                                  selected.handlerId === item.id
                                    ? styles.selected
                                    : ""
                                }
                                type="text"
                                onClick={() =>
                                  setSelected({
                                    kind: "handler",
                                    event: event as HookEventName,
                                    groupId: group.id,
                                    handlerId: item.id,
                                  })
                                }
                              >
                                {item.id} <Tag>{item.type}</Tag>
                              </Button>
                              <Button
                                danger
                                type="text"
                                size="small"
                                onClick={() =>
                                  setDraft(
                                    removeHandler(
                                      draft,
                                      event as HookEventName,
                                      group.id,
                                      item.id,
                                    ),
                                  )
                                }
                              >
                                删除
                              </Button>
                            </div>
                          ))}
                          <Select
                            className={styles.handlerSelect}
                            size="small"
                            placeholder="添加 Handler"
                            options={(
                              ["command", "http", "prompt"] as HookHandlerType[]
                            ).map((type) => ({
                              value: type,
                              label: type,
                              disabled:
                                type === "prompt" &&
                                !promptEvents.has(event as HookEventName),
                            }))}
                            onChange={(type: HookHandlerType) =>
                              setDraft(
                                addHandler(
                                  draft,
                                  event as HookEventName,
                                  group.id,
                                  type,
                                ),
                              )
                            }
                          />
                        </div>
                      ))}
                    </div>
                  ))}
                </aside>
                <main className={styles.detail}>
                  {selected.kind === "root" ? (
                    <div className={styles.editor}>
                      <h2>全局设置</h2>
                      <label className={styles.switchLine}>
                        启用 Hook
                        <Switch
                          checked={draft.enabled}
                          onChange={(enabled) =>
                            setDraft({ ...draft, enabled })
                          }
                        />
                      </label>
                      <p>
                        关闭后，配置将保留但 Default Agent 不执行任何 Hook。
                      </p>
                    </div>
                  ) : (
                    renderHandlerEditor() ?? (
                      <div className={styles.editor}>
                        <h2>Matcher Group</h2>
                        <p>选择一个 Handler 以编辑详细配置。</p>
                      </div>
                    )
                  )}
                </main>
              </div>
            ),
          },
          {
            key: "scripts",
            label: "脚本库",
            children: (
              <div className={styles.scripts}>
                <div className={styles.scriptActions}>
                  <label className={styles.uploadLabel}>
                    上传 Hook 脚本
                    <input
                      aria-label="上传 Hook 脚本"
                      type="file"
                      multiple
                      accept=".py,.sh,.bash,.zsh"
                      onChange={(event) => onFiles(event.target.files)}
                    />
                  </label>
                  <span>
                    仅接受 .py、.sh、.bash、.zsh；单文件最多 1 MB，一批最多 20
                    个。
                  </span>
                </div>
                <Table
                  rowKey="filename"
                  size="small"
                  dataSource={scripts}
                  pagination={false}
                  columns={[
                    { title: "脚本", dataIndex: "filename" },
                    {
                      title: "大小",
                      dataIndex: "size",
                      render: (value) => `${value} B`,
                    },
                    {
                      title: "SHA-256",
                      dataIndex: "sha256",
                      render: (value) => (
                        <code>{String(value).slice(0, 16)}…</code>
                      ),
                    },
                  ]}
                />
                {uploadResult && (
                  <div className={styles.uploadResult}>
                    {uploadResult.accepted.length > 0 && (
                      <p>已接收：{uploadResult.accepted.join("、")}</p>
                    )}
                    {uploadResult.warned.length > 0 && (
                      <p>扫描警告：{uploadResult.warned.join("、")}</p>
                    )}
                    {uploadResult.failed.map((item) => (
                      <p key={item.filename}>
                        失败：{item.filename} — {item.reason}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
      <Modal
        title="配置已被更新"
        open={conflictOpen}
        onCancel={() => setConflictOpen(false)}
        footer={
          <>
            <Button onClick={() => setConflictOpen(false)}>保留草稿</Button>
            <Button
              type="primary"
              onClick={() => {
                setConflictOpen(false);
                void load();
              }}
            >
              重新加载最新配置
            </Button>
          </>
        }
      >
        <p>其他用户已保存新的 Hook 配置。重新加载会丢弃当前草稿。</p>
      </Modal>
      <Modal
        title="确认覆盖脚本"
        open={overwriteOpen}
        onCancel={() => setOverwriteOpen(false)}
        onOk={() =>
          void upload(
            pendingFiles
              .filter((file) =>
                scripts.some((script) => script.filename === file.name),
              )
              .map((file) => file.name),
          )
        }
        okText="确认覆盖"
        confirmLoading={uploading}
      >
        <p>
          {pendingFiles
            .filter((file) =>
              scripts.some((script) => script.filename === file.name),
            )
            .map((file) => file.name)
            .join("、")}{" "}
          已存在。覆盖会影响之后的 Hook 事件。
        </p>
      </Modal>
      <Modal
        title="执行人工测试"
        open={testOpen}
        onCancel={() => {
          setTestOpen(false);
          setConfirmed(false);
          setTestResult(null);
        }}
        onOk={() => void runTest()}
        okText="执行测试"
        okButtonProps={{ disabled: !confirmed, loading: testing }}
      >
        <p>这会真实执行当前草稿中的一个 Handler，不会保存草稿或重载 Agent。</p>
        <Checkbox
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        >
          我确认将执行真实命令、HTTP 请求或模型调用
        </Checkbox>
        {testResult && (
          <pre className={styles.summary}>
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </Modal>
    </div>
  );
}

export default HookManagementPage;

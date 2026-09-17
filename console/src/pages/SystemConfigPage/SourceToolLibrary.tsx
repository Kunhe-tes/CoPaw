import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
  Upload,
} from "antd";
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";

import { sourceToolsApi } from "@/api/modules/sourceTools";
import type {
  SourceToolAuditEvent,
  SourceToolDraft,
  SourceToolMetadata,
  SourceToolVersion,
} from "@/api/modules/sourceTools";
import { useAppMessage } from "@/hooks/useAppMessage";

import styles from "./SourceToolLibrary.module.less";

interface SourceToolLibraryProps {
  sourceId: string;
}

export function SourceToolLibrary({ sourceId }: SourceToolLibraryProps) {
  const { message } = useAppMessage();
  const [activeTools, setActiveTools] = useState<SourceToolMetadata[]>([]);
  const [drafts, setDrafts] = useState<SourceToolDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [replaceDraftFile, setReplaceDraftFile] = useState<File | null>(null);
  const [replacePublishName, setReplacePublishName] = useState<string | null>(
    null,
  );
  const [history, setHistory] = useState<SourceToolVersion[]>([]);
  const [historyToolName, setHistoryToolName] = useState<string | null>(null);
  const [audit, setAudit] = useState<SourceToolAuditEvent[]>([]);
  const [auditOpen, setAuditOpen] = useState(false);
  const [scriptContent, setScriptContent] = useState<string | null>(null);
  const [manualResult, setManualResult] = useState<string | null>(null);
  const [manualTestName, setManualTestName] = useState<string | null>(null);
  const [manualArguments, setManualArguments] = useState("{}");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextActive, nextDrafts] = await Promise.all([
        sourceToolsApi.listEffective(),
        sourceToolsApi.listDrafts(),
      ]);
      setActiveTools(nextActive);
      setDrafts(nextDrafts);
    } catch {
      message.error("无法加载当前系统的工具库");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load, sourceId]);

  const upload = async (file: File, replaceDraft = false) => {
    setUploading(true);
    try {
      await sourceToolsApi.uploadDraft(file, replaceDraft);
      message.success("已创建未发布草稿，需手动发布后才会影响后续 Agent 运行");
      await load();
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 409 && !replaceDraft) {
        setReplaceDraftFile(file);
      } else {
        message.error((error as Error).message || "上传失败");
      }
    } finally {
      setUploading(false);
    }
  };

  const publish = async (name: string, confirmReplace = false) => {
    try {
      await sourceToolsApi.publishDraft(name, confirmReplace);
      message.success("工具已发布；仅后续 Agent 运行会使用新版本");
      setReplacePublishName(null);
      await load();
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 409 && !confirmReplace) {
        setReplacePublishName(name);
      } else {
        message.error((error as Error).message || "发布失败");
      }
    }
  };

  const showHistory = async (name: string) => {
    try {
      setHistory(await sourceToolsApi.history(name));
      setHistoryToolName(name);
    } catch {
      message.error("无法加载版本历史");
    }
  };

  const showAudit = async () => {
    try {
      setAudit(await sourceToolsApi.audit());
      setAuditOpen(true);
    } catch {
      message.error("无法加载审计记录");
    }
  };

  const showVersionContent = async (name: string, version: number) => {
    try {
      const response = await sourceToolsApi.downloadVersion(name, version);
      setScriptContent(response.content);
    } catch {
      message.error("无法读取脚本内容");
    }
  };

  return (
    <Card
      className={styles.library}
      title="系统工具库"
      extra={
        <Upload
          accept=".py,text/x-python"
          beforeUpload={(file) => {
            void upload(file);
            return false;
          }}
          disabled={uploading}
          maxCount={1}
          showUploadList={false}
        >
          <Button icon={<UploadOutlined />} loading={uploading} type="primary">
            上传 Python 脚本
          </Button>
        </Upload>
      }
    >
      <Alert
        showIcon
        type="info"
        message="仅支持单个 Python 文件（最大 1 MiB）"
        description="上传会先通过静态校验和强制安全扫描，形成未发布草稿。发布、替换和停用只影响后续 Agent 运行；此处不提供浏览器脚本编辑。"
      />
      {loading ? (
        <div className={styles.loading}><Spin /></div>
      ) : (
        <div className={styles.sections}>
          <section>
            <h3>未发布草稿</h3>
            {drafts.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有未发布草稿" />
            ) : (
              <div className={styles.rows}>
                {drafts.map((draft) => (
                  <div className={styles.row} key={draft.name}>
                    <div className={styles.copy}>
                      <strong>{draft.name}</strong>
                      <span>{draft.description}</span>
                      <code>{draft.content_digest.slice(0, 12)}</code>
                    </div>
                    <Space wrap>
                      <Button onClick={() => void publish(draft.name)} type="primary">
                        发布
                      </Button>
                      <Button
                        onClick={() => {
                          setManualArguments("{}");
                          setManualTestName(draft.name);
                        }}
                      >
                        手动测试
                      </Button>
                      <Button
                        danger
                        onClick={() => {
                          Modal.confirm({
                            title: "丢弃未发布草稿？",
                            content: "草稿脚本会被丢弃，仅保留元数据审计记录。",
                            okButtonProps: { danger: true },
                            onOk: async () => {
                              await sourceToolsApi.discardDraft(draft.name);
                              await load();
                            },
                          });
                        }}
                      >
                        丢弃
                      </Button>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className={styles.sectionHeading}>
              <h3>当前生效的系统工具</h3>
              <Button onClick={() => void showAudit()}>审计记录</Button>
            </div>
            {activeTools.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有生效的系统工具" />
            ) : (
              <div className={styles.rows}>
                {activeTools.map((tool) => (
                  <div className={styles.row} key={tool.name}>
                    <div className={styles.copy}>
                      <strong>{tool.name} <Tag color="blue">v{tool.version}</Tag></strong>
                      <span>{tool.description}</span>
                      <code>{tool.content_digest.slice(0, 12)}</code>
                    </div>
                    <Space wrap>
                      <Button onClick={() => void showHistory(tool.name)}>
                        历史
                      </Button>
                      <Button
                        danger
                        onClick={() => {
                          Modal.confirm({
                            title: "停用 " + tool.name + "？",
                            content: "唯一的系统工具会从后续 Agent 运行中移除；对内置工具的覆盖会恢复到代码定义的内置工具。",
                            okButtonProps: { danger: true },
                            onOk: async () => {
                              await sourceToolsApi.deactivate(tool.name);
                              await load();
                            },
                          });
                        }}
                      >
                        停用
                      </Button>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      <Modal
        open={replaceDraftFile !== null}
        title="替换已有草稿？"
        okText="替换草稿"
        onCancel={() => setReplaceDraftFile(null)}
        onOk={() => {
          if (replaceDraftFile) {
            void upload(replaceDraftFile, true);
          }
          setReplaceDraftFile(null);
        }}
      >
        同一工具只能保留一个未发布草稿。确认后会丢弃旧草稿脚本，并保留其审计元数据。
      </Modal>
      <Modal
        open={replacePublishName !== null}
        title="确认替换已发布工具？"
        okText="确认替换并发布"
        okButtonProps={{ danger: true }}
        onCancel={() => setReplacePublishName(null)}
        onOk={() => {
          if (replacePublishName) {
            void publish(replacePublishName, true);
          }
        }}
      >
        同名工具已在当前系统生效。确认后会创建新版本；已有版本仍会保留在历史中。
      </Modal>
      <Modal
        footer={null}
        open={historyToolName !== null}
        title={"版本历史：" + (historyToolName || "")}
        onCancel={() => setHistoryToolName(null)}
      >
        <div className={styles.history}>
          {history.map((version) => (
            <div key={version.version} className={styles.historyRow}>
              <span>v{version.version} · {version.content_digest.slice(0, 12)}</span>
              <Button
                icon={<DownloadOutlined />}
                onClick={() => void showVersionContent(version.name, version.version)}
              >
                查看/下载
              </Button>
            </div>
          ))}
        </div>
      </Modal>
      <Modal
        footer={null}
        open={auditOpen}
        title="系统工具审计记录"
        onCancel={() => setAuditOpen(false)}
      >
        {audit.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无审计记录" />
        ) : (
          <div className={styles.history}>
            {audit.map((event) => (
              <div className={styles.historyRow} key={event.timestamp + event.event}>
                <span>{event.event} · {event.tool_name}</span>
                <span>{event.actor || "unknown"}</span>
              </div>
            ))}
          </div>
        )}
      </Modal>
      <Modal
        footer={null}
        open={scriptContent !== null}
        title="脚本内容（只读）"
        onCancel={() => setScriptContent(null)}
      >
        <pre className={styles.script}>{scriptContent}</pre>
      </Modal>
      <Modal
        footer={null}
        open={manualResult !== null}
        title="草稿手动测试结果"
        onCancel={() => setManualResult(null)}
      >
        <pre className={styles.script}>{manualResult}</pre>
      </Modal>
      <Modal
        open={manualTestName !== null}
        title={"执行草稿测试：" + (manualTestName || "")}
        okText="确认执行"
        onCancel={() => setManualTestName(null)}
        onOk={async () => {
          if (!manualTestName) {
            return;
          }
          let input: Record<string, unknown>;
          try {
            input = JSON.parse(manualArguments) as Record<string, unknown>;
          } catch {
            message.error("测试输入必须是 JSON 对象");
            return;
          }
          if (
            typeof input !== "object" ||
            Array.isArray(input) ||
            input === null
          ) {
            message.error("测试输入必须是 JSON 对象");
            return;
          }
          try {
            const result = await sourceToolsApi.manualTest(
              manualTestName,
              input,
            );
            setManualResult(JSON.stringify(result.output, null, 2));
            setManualTestName(null);
          } catch (error) {
            message.error((error as Error).message || "手动测试失败");
          }
        }}
      >
        <Alert
          showIcon
          type="warning"
          message="测试会产生真实副作用"
          description="将使用当前 Agent Profile 的租户工作区、凭据和 Tool Guard/审批链执行草稿；默认输入为 {}。"
        />
        <label className={styles.inputLabel} htmlFor="source-tool-test-input">
          JSON 输入
        </label>
        <Input.TextArea
          id="source-tool-test-input"
          autoSize={{ minRows: 5, maxRows: 12 }}
          value={manualArguments}
          onChange={(event) => setManualArguments(event.target.value)}
        />
      </Modal>
    </Card>
  );
}

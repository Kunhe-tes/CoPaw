import {
  AudioOutlined,
  CloseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  LoadingOutlined,
  ProfileOutlined,
  ReloadOutlined,
  StopOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Alert, Button, Modal, Tooltip, Typography } from "antd";
import { type ReactNode, useCallback, useState } from "react";

import {
  emitChatInputAppendText,
  emitChatInputReplaceText,
} from "@/components/agentscope-chat/chatInputDraft";

import { VoiceRecorderTriggerContext } from "./context";
import styles from "./index.module.less";
import { buildVoiceSopPrompt } from "./sop";
import { formatRecordingDuration, useVoiceRecorder } from "./useVoiceRecorder";

const { Text, Title } = Typography;

function isBusy(status: ReturnType<typeof useVoiceRecorder>["status"]) {
  return (
    status === "requesting" ||
    status === "processing" ||
    status === "transcribing"
  );
}

export interface GlobalVoiceRecorderProps {
  children: ReactNode;
  enabled: boolean;
}

export default function GlobalVoiceRecorder({
  children,
  enabled,
}: GlobalVoiceRecorderProps) {
  const [replaceOpen, setReplaceOpen] = useState(false);
  const handleTranscriptionSuccess = useCallback((text: string) => {
    emitChatInputAppendText(text);
  }, []);
  const recorder = useVoiceRecorder({
    onTranscriptionSuccess: handleTranscriptionSuccess,
  });
  const recordingActive = recorder.status === "recording";
  const disabled =
    recorder.status === "unsupported" ||
    recorder.status === "requesting" ||
    recorder.status === "processing";

  const launcherLabel = recordingActive
    ? `正在录音 ${formatRecordingDuration(recorder.elapsedMs)}`
    : recorder.recording
    ? "打开语音录制"
    : "开始语音录制";

  const handleLauncherClick = useCallback(() => {
    if (recordingActive || recorder.recording || isBusy(recorder.status)) {
      recorder.setPanelOpen(!recorder.panelOpen);
      return;
    }
    void recorder.startRecording();
  }, [recorder, recordingActive]);

  const handleGenerateSop = () => {
    const sopPrompt = buildVoiceSopPrompt(recorder.transcript);
    if (!sopPrompt) {
      return;
    }

    emitChatInputReplaceText(sopPrompt);
  };

  const triggerControl = enabled
    ? {
        disabled,
        label: launcherLabel,
        loading:
          recorder.status === "requesting" || recorder.status === "processing",
        panelOpen: recorder.panelOpen,
        recording: recordingActive,
        unsupported: recorder.status === "unsupported",
        trigger: handleLauncherClick,
      }
    : null;

  const errorAlert = (() => {
    if (!recorder.error) {
      return null;
    }
    if (recorder.error.code === "permission-denied") {
      return (
        <Alert
          className={styles.notice}
          type="warning"
          showIcon
          message="未获得麦克风权限"
          description="请在浏览器网站设置中允许麦克风访问，然后重试。"
        />
      );
    }
    if (recorder.error.code === "device-interrupted" && recorder.recording) {
      return (
        <Alert
          className={styles.notice}
          type="warning"
          showIcon
          message="麦克风连接已中断，已保留中断前的录音。"
        />
      );
    }
    if (recorder.error.code === "transcription-failed") {
      return (
        <Alert
          className={styles.notice}
          type="error"
          showIcon
          message="转换失败"
          description="请检查接口配置、网络和 CORS 设置后重试，当前录音和转写结果未被清除。"
        />
      );
    }
    return (
      <Alert
        className={styles.notice}
        type="error"
        showIcon
        message="录音失败"
        description={
          recorder.error.code === "empty-audio"
            ? "没有采集到有效音频，请检查麦克风后重试。"
            : "请检查麦克风连接和浏览器权限后重试。"
        }
      />
    );
  })();

  return (
    <VoiceRecorderTriggerContext.Provider value={triggerControl}>
      {children}
      {enabled && (
        <div
          className={`${styles.root} ${styles.chatClearance}`}
          data-testid="global-voice-recorder"
        >
          {recorder.panelOpen && (
            <section className={styles.workspace} aria-label="语音录制面板">
              <div className={styles.header}>
                <Title level={5} className={styles.title}>
                  语音录制
                </Title>
                <Button
                  type="text"
                  size="small"
                  icon={<CloseOutlined />}
                  aria-label="关闭录音面板"
                  onClick={() => recorder.setPanelOpen(false)}
                />
              </div>

              <div className={styles.statusRow} aria-live="polite">
                {recordingActive && <span className={styles.recordingDot} />}
                {recorder.status === "requesting" && <LoadingOutlined spin />}
                {recorder.status === "processing" && <LoadingOutlined spin />}
                {recorder.status === "transcribing" && <LoadingOutlined spin />}
                {recorder.status === "permission-denied" && <WarningOutlined />}
                <Text>
                  {recordingActive
                    ? "正在录音"
                    : recorder.status === "requesting"
                    ? "正在请求麦克风权限…"
                    : recorder.status === "processing"
                    ? "正在生成 WAV 文件…"
                    : recorder.status === "transcribing"
                    ? "正在转换文字…"
                    : recorder.recording
                    ? "录音已生成"
                    : "点击开始后将请求麦克风权限"}
                </Text>
                {(recordingActive || recorder.recording) && (
                  <span className={styles.time}>
                    {formatRecordingDuration(
                      recordingActive
                        ? recorder.elapsedMs
                        : recorder.recording?.durationMs ?? 0,
                    )}
                  </span>
                )}
              </div>

              {recorder.durationWarning && recordingActive && (
                <Alert
                  type="warning"
                  showIcon
                  message="录音已超过 9 分钟，将在 10 分钟时自动停止。"
                />
              )}

              {recorder.stopReason === "limit" && recorder.recording && (
                <Alert
                  type="info"
                  showIcon
                  message="已达到 10 分钟上限，录音已自动停止。"
                />
              )}

              {errorAlert}

              {recorder.recording && (
                <>
                  <audio
                    className={styles.player}
                    src={recorder.recording.objectUrl}
                    controls
                    preload="metadata"
                    aria-label="录音播放控件"
                  />
                  <div className={styles.actions}>
                    <Button
                      icon={<DownloadOutlined />}
                      href={recorder.recording.objectUrl}
                      download={recorder.recording.file.name}
                    >
                      下载 WAV
                    </Button>
                    <Tooltip
                      title={
                        recorder.transcriptionConfigured
                          ? undefined
                          : "转写接口尚未配置"
                      }
                    >
                      <span>
                        <Button
                          type="primary"
                          icon={
                            recorder.status === "transcribing" ? (
                              <LoadingOutlined spin />
                            ) : (
                              <FileTextOutlined />
                            )
                          }
                          disabled={
                            !recorder.transcriptionConfigured ||
                            recorder.status === "transcribing"
                          }
                          onClick={() => void recorder.transcribe()}
                        >
                          {recorder.error?.code === "transcription-failed"
                            ? "重新转换"
                            : "转换文字"}
                        </Button>
                      </span>
                    </Tooltip>
                    <Button
                      icon={<ProfileOutlined />}
                      aria-label="生成SOP"
                      disabled={
                        !recorder.transcript ||
                        recorder.status === "transcribing"
                      }
                      onClick={handleGenerateSop}
                    >
                      生成SOP
                    </Button>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={() => setReplaceOpen(true)}
                      disabled={recorder.status === "transcribing"}
                    >
                      重新录制
                    </Button>
                    <Button
                      danger
                      type="text"
                      icon={<DeleteOutlined />}
                      onClick={recorder.discardRecording}
                      disabled={recorder.status === "transcribing"}
                    >
                      清除
                    </Button>
                  </div>

                  {!recorder.transcriptionConfigured && (
                    <Alert
                      className={styles.notice}
                      type="info"
                      showIcon
                      message="转写接口尚未配置"
                      description="请在前端转写适配器中补充接口 URL、请求入参和响应文字映射。未配置时不会发送网络请求。"
                    />
                  )}
                </>
              )}

              {!recorder.recording && !recordingActive && (
                <div className={styles.actions}>
                  <Button
                    type="primary"
                    icon={<AudioOutlined />}
                    loading={recorder.status === "requesting"}
                    disabled={recorder.status === "unsupported"}
                    onClick={() => void recorder.startRecording()}
                  >
                    {recorder.status === "permission-denied" ||
                    recorder.status === "error"
                      ? "重试"
                      : "开始录音"}
                  </Button>
                </div>
              )}

              {recordingActive && (
                <div className={styles.actions}>
                  <Button
                    danger
                    type="primary"
                    icon={<StopOutlined />}
                    onClick={() => void recorder.stopRecording()}
                  >
                    停止录音
                  </Button>
                </div>
              )}
            </section>
          )}

          <Modal
            title="替换当前录音？"
            open={replaceOpen}
            okText="清除并重新录制"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onCancel={() => setReplaceOpen(false)}
            onOk={() => {
              setReplaceOpen(false);
              void recorder.startRecording(true);
            }}
          >
            继续后将清除当前 WAV 文件和转写结果，此操作无法撤销。
          </Modal>
        </div>
      )}
    </VoiceRecorderTriggerContext.Provider>
  );
}

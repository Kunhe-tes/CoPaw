import { LoadingOutlined } from "@ant-design/icons";
import { IconButton } from "@agentscope-ai/design";
import { SparkMicLine, SparkMicOnLine } from "@agentscope-ai/icons";
import { Tooltip } from "antd";

import { useVoiceRecorderTrigger } from "./context";

export default function VoiceRecorderTrigger() {
  const recorder = useVoiceRecorderTrigger();
  if (!recorder) {
    return null;
  }

  const icon = recorder.loading ? (
    <LoadingOutlined spin />
  ) : recorder.recording ? (
    <SparkMicOnLine />
  ) : (
    <SparkMicLine />
  );
  const guidance = recorder.unsupported
    ? "当前浏览器不支持所需的麦克风录音 API"
    : recorder.label;

  return (
    <Tooltip title={guidance}>
      <span
        role={recorder.unsupported ? "note" : undefined}
        tabIndex={recorder.unsupported ? 0 : undefined}
        aria-label={recorder.unsupported ? guidance : undefined}
      >
        <IconButton
          aria-expanded={recorder.panelOpen}
          aria-label={recorder.label}
          bordered={false}
          disabled={recorder.disabled}
          icon={icon}
          onClick={recorder.trigger}
        />
      </span>
    </Tooltip>
  );
}

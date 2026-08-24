import { LoadingOutlined } from "@ant-design/icons";
import { SparkMicLine, SparkMicOnLine } from "@agentscope-ai/icons";
import { Tooltip } from "antd";

import { ComposerQuickMenuItem } from "@/components/agentscope-chat/ComposerQuickMenu";

import {
  type VoiceRecorderTriggerControl,
  useVoiceRecorderTrigger,
} from "./context";

export interface VoiceRecorderQuickMenuItemProps {
  control?: VoiceRecorderTriggerControl | null;
}

export default function VoiceRecorderQuickMenuItem({
  control,
}: VoiceRecorderQuickMenuItemProps) {
  const contextControl = useVoiceRecorderTrigger();
  const recorder = control === undefined ? contextControl : control;
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
        <ComposerQuickMenuItem
          icon={icon}
          label="语音录制"
          disabled={recorder.disabled}
          onClick={recorder.trigger}
        />
      </span>
    </Tooltip>
  );
}

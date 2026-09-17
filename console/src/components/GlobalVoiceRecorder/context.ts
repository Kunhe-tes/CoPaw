import { createContext, useContext } from "react";

export interface VoiceRecorderTriggerControl {
  disabled: boolean;
  label: string;
  loading: boolean;
  panelOpen: boolean;
  recording: boolean;
  unsupported: boolean;
  trigger: () => void;
}

export const VoiceRecorderTriggerContext =
  createContext<VoiceRecorderTriggerControl | null>(null);

export function useVoiceRecorderTrigger(): VoiceRecorderTriggerControl | null {
  return useContext(VoiceRecorderTriggerContext);
}

import type { IAgentScopeRuntimeWebUIInputData } from "@/components/agentscope-chat";
import type {
  SkillMentionItem,
  SkillMentionsData,
} from "@/components/agentscope-chat/SkillMentions/useSkillMentions";

interface CreateWelcomeSkillMentionsOptions {
  contextReferences: SkillMentionItem[];
  contextReferencesError?: boolean;
  contextReferencesLoading: boolean;
  isComposingRef: { current: boolean };
  loadContextReferences: (query: string) => void;
  pendingContextReferencesRef: { current: SkillMentionItem[] };
  selectedContextReferences: SkillMentionItem[];
  setSelectedContextReferences: (items: SkillMentionItem[]) => void;
}

export function createWelcomeSkillMentions({
  contextReferences,
  contextReferencesError,
  contextReferencesLoading,
  isComposingRef,
  loadContextReferences,
  pendingContextReferencesRef,
  selectedContextReferences,
  setSelectedContextReferences,
}: CreateWelcomeSkillMentionsOptions): {
  beforeSubmit: (
    inputData: IAgentScopeRuntimeWebUIInputData,
  ) => Promise<IAgentScopeRuntimeWebUIInputData | false>;
  skillMentions: SkillMentionsData;
} {
  const beforeSubmit = async (inputData: IAgentScopeRuntimeWebUIInputData) => {
    if (isComposingRef.current) return false;
    pendingContextReferencesRef.current = selectedContextReferences;
    setSelectedContextReferences([]);
    return inputData;
  };

  return {
    beforeSubmit,
    skillMentions: {
      items: contextReferences,
      error: contextReferencesError ?? false,
      selected: selectedContextReferences,
      loading: contextReferencesLoading,
      onOpen: loadContextReferences,
      onChange: setSelectedContextReferences,
      onRetry: () => loadContextReferences(""),
    },
  };
}

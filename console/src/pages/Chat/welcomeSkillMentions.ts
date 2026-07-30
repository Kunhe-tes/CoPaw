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
  beforeSubmit: () => Promise<boolean>;
  skillMentions: SkillMentionsData;
} {
  const beforeSubmit = async () => {
    if (isComposingRef.current) return false;
    pendingContextReferencesRef.current = selectedContextReferences;
    setSelectedContextReferences([]);
    return true;
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

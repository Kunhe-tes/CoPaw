import type {
  SkillMentionItem,
  SkillMentionsData,
} from "@/components/agentscope-chat/SkillMentions/useSkillMentions";

interface CreateWelcomeSkillMentionsOptions {
  effectiveSkills: SkillMentionItem[];
  effectiveSkillsError?: boolean;
  effectiveSkillsLoading: boolean;
  isComposingRef: { current: boolean };
  loadEffectiveSkills: () => void;
  pendingSelectedSkillNamesRef: { current: string[] };
  selectedSkillNames: string[];
  setSelectedSkillNames: (names: string[]) => void;
}

export function createWelcomeSkillMentions({
  effectiveSkills,
  effectiveSkillsError,
  effectiveSkillsLoading,
  isComposingRef,
  loadEffectiveSkills,
  pendingSelectedSkillNamesRef,
  selectedSkillNames,
  setSelectedSkillNames,
}: CreateWelcomeSkillMentionsOptions): {
  beforeSubmit: () => Promise<boolean>;
  skillMentions: SkillMentionsData;
} {
  const beforeSubmit = async () => {
    if (isComposingRef.current) return false;
    pendingSelectedSkillNamesRef.current = selectedSkillNames;
    setSelectedSkillNames([]);
    return true;
  };

  return {
    beforeSubmit,
    skillMentions: {
      items: effectiveSkills,
      error: effectiveSkillsError ?? false,
      selected: selectedSkillNames,
      loading: effectiveSkillsLoading,
      onOpen: loadEffectiveSkills,
      onChange: setSelectedSkillNames,
      onRetry: loadEffectiveSkills,
    },
  };
}

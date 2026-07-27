import type {
  SkillMentionItem,
  SkillMentionsData,
} from "@/components/agentscope-chat/SkillMentions/useSkillMentions";

interface CreateWelcomeSkillMentionsOptions {
  effectiveSkills: SkillMentionItem[];
  effectiveSkillsLoading: boolean;
  isComposingRef: { current: boolean };
  loadEffectiveSkills: () => void;
  pendingSelectedSkillNamesRef: { current: string[] };
  selectedSkillNames: string[];
  setSelectedSkillNames: (names: string[]) => void;
}

export function createWelcomeSkillMentions({
  effectiveSkills,
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
      selected: selectedSkillNames,
      loading: effectiveSkillsLoading,
      onOpen: loadEffectiveSkills,
      onChange: (names: string[]) => setSelectedSkillNames(names.slice(0, 5)),
    },
  };
}

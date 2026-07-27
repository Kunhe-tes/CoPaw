# Console skill selection uses trusted directives

Console chat treats an ordered `selected_skill_names` list as user intent, not as text embedded in the message. The server resolves every requested name against the target Agent's console **Skill Runtime View**, discards unavailable or unreadable entries, de-duplicates remaining **Skill Runtime Identifiers** while preserving first-selection order, and injects one trusted `<SKILL-USE-V1>` block per result. Each block contains only the runtime name, description, and server-resolved absolute `SKILL.md` path; it directs the Agent to read all selected documents in order before task execution instead of embedding full skill documents in the prompt.

**Consequences**

- A turn may retain up to five user selections, including duplicates, while each runtime skill is directed only once. The browser never supplies skill paths, descriptions, or document content.
- A selection is discarded when it is no longer effective or readable at turn start; the ordinary chat request still proceeds, and no special unavailable-selection record is retained.
- Selection records intent and may be shown to the user, but **Actual Skill Use** and tool-call attribution remain evidence-based. The first rollout deliberately has no runtime guard that verifies the Agent read the selected document before acting.
- Console control commands remain outside this protocol: they do not submit skill selections and clear any current selection labels after execution.
- When at least one directive is injected, its Chinese-response requirement applies to the whole turn; ordinary turns retain their existing language behavior.

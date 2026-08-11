# Console inline skill tags preserve trusted selection

Console chat represents each panel-confirmed skill choice twice: as a visible atomic `@name` tag in the user message and as ordered `selected_skill_names` context. The tag makes the intended capability readable in the prompt and history, while only the structured list is resolved against the Skill Runtime View and permitted to produce trusted skill-use directives; raw or pasted `@name` text never selects a skill.

**Consequences**

- Deleting an atomic tag removes its corresponding structured selection occurrence, including when a skill was selected more than once.
- The server must never infer a selection from message text, so ordinary discussion of `@name` cannot alter runtime behavior.

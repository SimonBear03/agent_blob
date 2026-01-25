# Skill: PKM Note Creation

**Purpose**: Guide the agent to create well-structured PKM notes using filesystem tools.

## When to Use This Skill

Activate this skill when:
- User asks to "create a note" or "save to PKM"
- User wants to capture research, ideas, or conversation insights
- User mentions inbox, library, or project notes

## How It Works

This skill uses the general `filesystem.write` tool to create notes. The agent should:
1. Determine the appropriate note type and location
2. Generate the note content with proper YAML frontmatter
3. Use `filesystem.write` to save the note to the PKM vault

## Note Types and Locations

### 1. Inbox Research Notes (`888_inbox/`)
For raw captures, research sessions, and chat exports.

**Filename pattern**: `<topic>_inbox_research_YYYY_MM_DD.md`

**Structure**:
```markdown
---
title: "<Topic> – Inbox Research"
date: YYYY-MM-DD
tags: [<domain>, <domain>/<topic>]
---

# <Topic> – Inbox Research

## Context
Why this research matters and what prompted it.

## Questions
- Main question 1?
- Main question 2?

## Key Learnings
Brief snapshot of what has been discovered.

## Notes
Detailed notes, evidence, sources, and exploration.

## Next Steps
- [ ] Action item 1
- [ ] Action item 2

## Candidates for Library
Concepts that might become permanent notes in `999_library/`:
- [[concept_name]] - brief description
```

### 2. Library Notes (`999_library/`)
For distilled, reusable knowledge.

**Locations**:
- `999_library/methods/` - processes, workflows, techniques
- `999_library/topics/` - concepts, ideas, domains
- `999_library/frameworks/` - systems, mental models

**Filename**: `<concept_name>.md` (lowercase snake_case)

**Structure**:
```markdown
---
title: "<Concept Name>"
date: YYYY-MM-DD
tags: [<domain>, <domain>/<topic>]
---

# <Concept Name>

## Summary
Clear one-paragraph explanation of the concept.

## Context
When and why to use this. What problem does it solve?

## Key Points
- Point 1
- Point 2
- Point 3

## How to Use
Concrete steps or examples of applying this concept.

## Related Notes
- [[related_note_1]]
- [[related_note_2]]

## Source
Where this idea came from (ChatGPT/Gemini/web/book/self).
```

### 3. Project Notes (`910_projects/`)
For concrete deliverables with goals and next actions.

**Structure**:
```markdown
---
title: "<Project Name>"
date: YYYY-MM-DD
tags: [<domain>, <domain>/<topic>]
---

# <Project Name>

## Goal
What success looks like.

## Current Status
Where things stand now.

## Next Actions
- [ ] Concrete task 1
- [ ] Concrete task 2

## Linked Notes
- [[relevant_inbox_note]]
- [[relevant_library_note]]
```

## Output Format

When creating a PKM note, construct the full Markdown content with:

1. **YAML frontmatter** (lines 1-5):
   ```
   ---
   title: "Note Title"
   date: YYYY-MM-DD
   tags: [domain, domain/topic]
   ---
   ```

2. **Content sections** with proper headings and markdown formatting

3. **File path**: Construct the full path within `PKM_ROOT` environment variable
   - Inbox notes: `${PKM_ROOT}/888_inbox/<filename>.md`
   - Library notes: `${PKM_ROOT}/999_library/<subfolder>/<filename>.md`
   - Project notes: `${PKM_ROOT}/910_projects/<filename>.md`

4. **Use filesystem.write tool** to save the rendered markdown to the target path

## Best Practices

1. **Naming**: Use lowercase snake_case for all filenames
2. **Dates**: Use `YYYY-MM-DD` format consistently
3. **Tags**: Align with user's taxonomy (check `000_system/asset_taxonomy.md` if available)
4. **Wikilinks**: Reference related notes using `[[note_name]]` syntax
5. **Sections**: Use clear, descriptive headings
6. **Conciseness**: Keep library notes focused and actionable
7. **Context**: Always include enough context for future you to understand

## Example Interaction

**User**: "Create an inbox note about our conversation on agent safety."

**Agent**: "I'll create an inbox research note capturing our discussion on agent safety."

[Agent constructs markdown content with frontmatter and sections]

[Agent uses filesystem.write tool with path: `${PKM_ROOT}/888_inbox/agent_safety_inbox_research_2026_01_26.md`]

**Agent**: "I've created `agent_safety_inbox_research_2026_01_26.md` in your `888_inbox/` folder with sections covering our key discussion points, safety principles we identified, and next steps for implementation."

## Questions to Ask

Before creating a note, consider asking:
- "What's the main topic or title for this note?"
- "Is this for immediate capture (inbox), long-term reference (library), or an active project?"
- "Are there specific tags or related notes you want me to link?"
- "Should I include any specific sections or structure?"

## Error Prevention

- Use `filesystem.list` to check if a similar note already exists before creating a new one
- Construct paths using the `PKM_ROOT` environment variable
- Ensure the filename follows conventions (lowercase snake_case with .md extension)
- Verify frontmatter YAML syntax is correct (proper quotes, array format for tags)
- Use `filesystem.read` to check existing note structure if unsure about format

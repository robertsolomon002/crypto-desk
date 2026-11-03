# Prompts

Versioned prompts. A prompt used in production is never edited: copy it to `_v2` and change the code to point at the new file.

- `agent_v1.md`: chat agent system prompt (Stage 5.1)
- `desk/`: the multi-agent desk (Stage 5.3, D47).
  - `technical_v1`, `context_v1`: the analysts. They research with tools, then write a report of findings.
  - `bull_v1`, `bear_v1`: one file per side, used for both the opening and the rebuttal through `{phase}`.
  - `head_v1`: the Decision 8 signal.
  - Placeholders: `{coin}`, `{coin_name}` and `{today}` everywhere, plus `{max_tool_calls}` for the analysts, `{phase}` for the debaters and `{confidence_min}`/`{confidence_max}` for the head.
- `brief_v1.md`: weekly brief writer (Stage 7.1)
- `mco_extract_v1.md`: MCO video extraction (Stage 6.1)

Headlines, transcripts and video content are untrusted data. Prompts must say so and must ignore instructions found inside them.

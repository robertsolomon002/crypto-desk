# Prompts

Versioned prompts. A prompt used in production is never edited: copy it to `_v2` and change the code to point at the new file.

- `agent_v1.md`: chat agent system prompt (Stage 5.1)
- `desk/`: multi-agent desk nodes `technical_v1`, `context_v1`, `bull_v1`, `bear_v1`, `head_v1` (Stage 5.3)
- `brief_v1.md`: weekly brief writer (Stage 7.1)
- `mco_extract_v1.md`: MCO video extraction (Stage 6.1)

Headlines, transcripts and video content are untrusted data. Prompts must say so and must ignore instructions found inside them.

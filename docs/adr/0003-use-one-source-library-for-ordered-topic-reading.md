---
status: accepted
---

# Use one Source Library for ordered Topic Reading and anchored Synthesis

FOCUS stores every registered Reading Source exactly once under `sources/<source-id>/`. A Topic manifest is the sole membership authority and preserves an ordered list of Source IDs; `source.yaml` does not duplicate Topic membership. Sources may be registered before any Topic and later attached to several Topics without copying Parser Bundles, Reading Plans, Records, Notes, or translations.

Source Title, Source Short Name, Source ID, Source Identity, and MinerU Parser Task ID are separate. Registration resolves the exact title and stable semantic short name after parsing, then allocates `<short-name>-paper` or `<short-name>-article`. A genuine name collision uses a trustworthy publication year first and a numeric suffix otherwise. Identical canonical article URLs and identical Paper originals reuse the installed Source.

Invoking `article-parser` or `paper-parser` with a URL or selected file is the authorization for the required MinerU request. This decision supersedes ADR-0002's requirement for a second explicit fetch/upload authorization. Network, credential, publisher access, MinerU, polling, and Bundle validation failures return direct typed errors; Article parsing never bypasses access controls or adds publisher-specific adapters.

`focus-map` keeps installed Plans under their Source and accepts private draft transport only through stdin; it exposes no temporary draft path or receipt. `focus-read topic <topic-id>` traverses the Topic's ordered Sources using only `current_topic_id` plus the existing per-Source cursors. A Source completed anywhere is complete in every Topic unless explicitly reinitialized for rereading.

An explicitly requested Topic Synthesis may store concise claims with Source IDs and Source Anchors under `topics/<topic-id>/synthesis/`. Retrieval begins with bounded filesystem search over that Topic. This narrows ADR-0002's derived-knowledge non-goal: Phase 1 permits this source-anchored derived output, but still excludes automatic rewriting, copied source assets, SQLite or FTS indexes, embeddings, vector databases, knowledge graphs, receipts, history logs, and compatibility state.

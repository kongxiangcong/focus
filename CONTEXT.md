# FOCUS Reading Workspace

FOCUS is a topic-driven workspace for organizing papers, planning close reading, maintaining a reading position, and requesting explanations. It records navigation and reader operations without evaluating the reader or claiming that content was understood.

## Language

**Topic**:
A named collection that organizes related Papers without owning or copying their assets.
_Avoid_: Course, learning path, knowledge domain

**Paper**:
One locally registered scholarly work and its reusable source-derived assets.
_Avoid_: Learning object, assessment subject

**Paper ID**:
A stable readable slug assigned when a Paper enters the Workspace, with a numeric suffix used only to resolve collisions. It never contains or depends on a content hash.
_Avoid_: Full title, source hash, mutable display name

**Parser Bundle**:
The canonical parser-produced PDF, Markdown, referenced images, metadata, and structural validation generated directly inside one Paper's Workspace directory. It contains no content hash and is treated as immutable after successful generation.
_Avoid_: Temporary extraction, duplicate source tree, Reading Plan

**Blog Output**:
A Paper-local explanatory article generated from its Parser Bundle and stored beside that bundle. It never owns or modifies Reading Plans, Chunk Records, Notes, Explanation Sessions, or Workspace pointers.
_Avoid_: Reading Plan, Chunk presentation, source bundle

**Reading Plan**:
The fixed ordered definition of which parts of a Paper will be read and how they are divided into Reading Chunks.
_Avoid_: Curriculum, mastery plan, knowledge map

**Plan Glossary**:
The source-to-translation terminology table belonging to one Reading Plan. An explicit reader correction affects future uncached translations without rewriting prior cached presentations.
_Avoid_: Knowledge graph, learner vocabulary, global terminology authority

**Reading Chunk**:
One stable, source-anchored unit in a Reading Plan that can be presented to the reader as a whole.
_Avoid_: Lesson, checkpoint, mastery node

**Chunk Record**:
The private persisted record for one Reading Chunk, containing its source location, cached translation, Reader Notes, and Discussion Notes without any reader evaluation.
_Avoid_: Lesson record, learner record, assessment record

**Reading Cursor**:
The persisted position identifying the Reading Chunk currently selected in a Reading Plan.
_Avoid_: Learning progress, understanding state, mastery state

**Guided Reading**:
The interaction context that presents the Reading Chunk selected by the Reading Cursor and accepts reading navigation operations.
_Avoid_: Lesson, study session, assessment

**Continue Reading**:
A Guided Reading operation that advances the Reading Cursor by one Reading Chunk.
_Avoid_: Continue, confirmed, understood, mastered, passed

**Inline Reading Discussion**:
A brief question-and-answer exchange inside Guided Reading when the reader has not explicitly opened an Explanation Session. It leaves the Reading Cursor unchanged and may contribute a note to the current Reading Chunk.
_Avoid_: Explanation Session, assessment, checkpoint

**Explanation Request**:
A reader operation that opens an Explanation Session for selected Paper content without changing the Reading Cursor.
_Avoid_: Remediation, assessment, checkpoint

**Explanation Session**:
One private, persisted sequence of raw reader questions and model responses. It never owns or changes the Reading Cursor and contains no reader evaluation or Reading Chunk association.
_Avoid_: Guided Reading, remediation, assessment, cognitive evidence

**Explanation Source**:
Paper-wide or external material consulted internally to answer an Explanation Request. Phase 1 does not persist separate source bookkeeping or require source-by-source labeling in the visible response.
_Avoid_: Reading Chunk association, learner evidence, explanation progress

**Current Explanation Session**:
The Explanation Session currently selected to receive a Continue Explanation operation. The selection is only a file reference and expresses no explanation progress, completion, or reader state.
_Avoid_: Explanation progress, active learning state, current reading position

**Continue Explanation**:
An Explanation Session operation that appends the next explanatory exchange without changing the Reading Cursor.
_Avoid_: Continue, continue reading, advance

**Reader Note**:
Reader-authored remarks, reactions, or reflections attached to a Reading Chunk without interpretation or evaluation by FOCUS.
_Avoid_: Feedback score, checkpoint answer, cognitive evidence

**Discussion Note**:
A neutral model-written recap of an Inline Reading Discussion attached to the current Reading Chunk. It records what was asked and answered without inferring what the reader understands, misunderstands, or has mastered.
_Avoid_: Reader Note, understanding summary, assessment result, cognitive evidence

**Emphasis Note**:
Content the reader explicitly marks as important within a Reading Chunk. The importance comes only from the reader's instruction, never from model-selected prioritization.
_Avoid_: Model highlight, importance score, learning priority

**Private Reading Data**:
Reader-specific cursor, cached presentation, Notes, and Explanation Session data that stays in the local Workspace and is excluded from the public project.
_Avoid_: Public fixture, reusable project asset, user profile

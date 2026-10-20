# Step 2: pure component extraction

The library `<main>` moved from `WorkspaceApp.tsx` to `library/LibraryPage.tsx` with an explicit `LibraryPageProps` data/handler contract. State, business functions and confirmation dialogs remain in WorkspaceApp. The extracted JSX was compared byte-for-byte with step 1 and is identical. No test, CSS, text or event-handler changes were made.

- WorkspaceApp: net reduction of 57 lines.
- `pnpm reader:typecheck`: PASS.
- `pnpm reader:build`: PASS (existing bundle warning).
- `pnpm reader:test`: 85 reader-ui tests passed, 1 existing timeout failed; recursive execution stops before standalone as in the baseline.
- `pnpm --filter @focus/standalone test --maxWorkers=1 --testTimeout=20000`: PASS, 104 tests / 6 files. Existing tests were not edited.
- Required confirmed/preparation browser checks remain blocked by the pre-existing missing fixture script. No browser pass is claimed. Screenshot evidence was waived.

## Usage

### For Translators

This section is for people who only need to translate content.
You do not need to understand the Python code in this repository.

#### 1. Install The Tooling Once

When using this repository for the first time, run:

```shell
make install-dev
```

This creates `.venv` if needed and installs the required Python packages into it.

#### 2. Refresh The Translation Tree From Latest Files (Optional)

Most translators can skip this step, because the collaboration tree is usually
prepared in advance.

If you need to rebuild the tree structure from the latest source files, first
make sure the latest PO and KM files are placed under `files/`.

- The PO file can be downloaded from:
  `https://localize.ds-wizard.org/projects/knowledge-models/common-dsw-knowledge-model/zh_Hant/`
- The KM file can be exported from your local DSW instance.

Then run:

```shell
make export-tree-force
```

This rebuilds the collaboration tree under `translation/zh_Hant/tree` from the
contents of `files/` and discards current tree content after confirmation.

This step prepares the tree only. It does not refresh the generated PO or diff
outputs. Those are refreshed later by `make sync`, `make tree-to-po`, or
`make review-po`.

#### 3. Open The Translation Tree

After the tree has been prepared, go to `translation/zh_Hant/tree`.

- Each folder represents one node in the knowledge model.
- Each folder contains `_uuid.txt`.
- If the node has translatable content, it also contains `translation.md`.
- Tree backups are stored separately under `translation/zh_Hant/backups/tree`.

#### 4. Edit Only `translation.md`

Open `translation.md` and edit only the `Translation (zh_Hant)` blocks.

- Do not change the UUID.
- Do not rename folders.
- Do not edit the `Source (en)` blocks unless you are intentionally fixing source text.
- Do not type translated text outside the `~~~text` fences.

Each file keeps fields in a stable order such as:

- `title`
- `label`
- `text`
- `advice`

#### 5. Check What Is Still Untranslated

```shell
make status
```

This shows:

- which folders still have untranslated fields
- the first few untranslated fields in tree order

#### 6. Sync Repeated English Strings And Refresh The Final PO

```shell
make sync
```

This updates other nodes that share the same original PO translation block,
refreshes `translation/zh_Hant/builds/final_translated.po`, and also refreshes
`translation/zh_Hant/reviews/final_translated.diff` so you can review what changed.

If a fence is broken or text is typed outside the fenced translation blocks,
the command stops, reports the broken file, and restores that file from its
last known-good backup.

If a translator accidentally deletes `translation.md`, `_uuid.txt`, or even a
whole node folder, the tool attempts to restore it automatically from the tree
manifest and the backup store before continuing.

If you want this to keep running every 10 seconds while you work:

```shell
make sync-watch
```

This keeps refreshing both the final PO and the diff file on each sync pass.
When a file is corrupt, watch mode reports the error, restores the last valid
file when possible, and keeps running for the next pass.

#### 7. Run Translation Tests And Open A PR

Before running translation tests, make sure you have already refreshed the
generated PO and diff outputs with either:

```shell
make sync
```

or:

```shell
make sync-watch
```

Then run:

```shell
make test-translation
```

This verifies that:

- `translation/zh_Hant/tree` is structurally valid
- the checked-in tree and generated PO are still in sync
- the checked-in diff matches the current PO review
- every checked-in `translation.md` has a matching backup

In normal translation work, `make test-translation` should pass after
`make sync` or `make sync-watch`.

If the tests pass, open a pull request with your translation changes.

If the tests do not pass, please notify the developer or project maintainer
and report the problem instead of trying to work around it manually.

#### 8. Upload The Final PO (Optional)

After the translation pull request has been merged, you can optionally upload
`translation/zh_Hant/builds/final_translated.po` manually to:

`https://localize.ds-wizard.org/projects/knowledge-models/common-dsw-knowledge-model/zh_Hant/`

If needed, ask the developer or project maintainer to run final validation
before upload.

### For Developers

This section is for maintaining the tooling and preparing final deliverables.

#### Show Available Targets

```shell
make help
```

#### Install Dev Tools

```shell
make install-dev
```

This installs the packages listed in `config/requirements.txt` into `.venv`.

#### Check Python Syntax

```shell
make compile
```

This checks whether the Python files under `src/` can be compiled successfully.

#### Run Lint

```shell
make lint
```

#### Run Unit Tests

```shell
make test
```

This runs the pytest suite for:

- infrastructure and CLI behavior
- translation tree and PO consistency

#### Run Infrastructure Unit Tests

```shell
make test-infra
```

#### Run Translation Unit Tests

```shell
make test-translation
```

#### Export Translation Tree

```shell
make export-tree
```

This writes a folder tree that mirrors the knowledge-model structure.

- Folder names use the node `title` / `label` / `name`.
- Nodes that only have `description` use the related `targetUuid` / `resourcePageUuid` node name as the folder label.
- Every node folder contains `_uuid.txt`.
- Translatable fields are grouped into a single `translation.md` per folder.
- Inside `translation.md`, each field is shown in a stable order such as `title -> label -> text -> advice`.
- The export root also contains `_translation_tree.json` for validation and re-import.
- Re-running export preserves existing translations by default.

If you intentionally want to rebuild the tree from the supplied PO and discard current tree content:

```shell
make export-tree-force
```

This will show a warning and require typing `yes`.

#### Build PO From Translation Tree

```shell
make tree-to-po
```

This also stops and restores the affected `translation.md` if a fence is
broken or text appears outside fenced translation blocks.

#### Review PO Differences

```shell
make review-po
```

This compares `translation/zh_Hant/builds/final_translated.po` with the original PO
template and writes a unified diff to
`translation/zh_Hant/reviews/final_translated.diff`.

Use this when you want to confirm that only `msgstr` values changed.

#### Validate Final Output

```shell
make validate
```

#### Optional Final Round-Trip Workflow

```shell
make workflow
```

This is only for a final smoke test or a full round-trip check.
You do not need to run it while translation is still in progress.

### Output Layout

The repository now keeps collaboration files and generated files under:

- `translation/zh_Hant/tree`
- `translation/zh_Hant/builds`
- `translation/zh_Hant/reviews`
- `translation/zh_Hant/reports`
- `translation/zh_Hant/backups`

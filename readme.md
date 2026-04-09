## Usage

### For Translators

This section is for people who only need to translate content.
You do not need to understand the Python code in this repository.

#### 1. Prepare The Latest Source Files

Make sure the latest PO and KM files are placed under `files/`.

- The PO file can be downloaded from:
  `https://localize.ds-wizard.org/projects/knowledge-models/common-dsw-knowledge-model/zh_Hant/`
- The KM file can be exported from your local DSW instance.

#### 2. Prepare The Translation Tree

```shell
make export-tree
```

This prepares the folder tree under `output/tree`.

#### 3. Open The Translation Tree

After the tree has been prepared, go to `output/tree`.

- Each folder represents one node in the knowledge model.
- Each folder contains `_uuid.txt`.
- If the node has translatable content, it also contains `translation.md`.
- The tool keeps hidden backups under `output/.tree_backups/`, outside the tree.

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
refreshes `output/final_translated.po`, and also refreshes
`output/final_translated.diff` so you can review what changed.

If a fence is broken or text is typed outside the fenced translation blocks,
the command stops, reports the broken file, and restores that file from its
last known-good backup.

If a translator accidentally deletes `translation.md`, `_uuid.txt`, or even a
whole node folder, the tool attempts to restore it automatically from the tree
manifest and the hidden backup store before continuing.

If you want this to keep running every 10 seconds while you work:

```shell
make sync-watch
```

This keeps refreshing both the final PO and the diff file on each sync pass.
When a file is corrupt, watch mode reports the error, restores the last valid
file when possible, and keeps running for the next pass.

#### 7. Upload The Final PO

When translation is finished, upload `output/final_translated.po` to:

`https://localize.ds-wizard.org/projects/knowledge-models/common-dsw-knowledge-model/zh_Hant/`

If needed, ask the developer or project maintainer to run final validation before upload.

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

- PO to tree export coverage
- tree to PO round-trip integrity
- shared-string synchronization behavior

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

This compares `output/final_translated.po` with the original PO template and
writes a unified diff to `output/final_translated.diff`.

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

## Usage

### Export Translation Tree

```shell
python3 src/po_json_tree.py \
  --po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po \
  --json files/dsw_root_2.7.0.km \
  --out-dir output/tree
```

This writes a folder tree that mirrors the knowledge-model structure.

- Folder names use the node `title` / `label` / `name`.
- Nodes that only have `description` use the related `targetUuid` / `resourcePageUuid` node name as the folder label.
- Every node folder contains `_uuid.txt`.
- Translatable fields are grouped into a single `translation.md` per folder.
- Inside `translation.md`, each field is shown in a stable order such as `title -> label -> text -> advice`.
- The export root also contains `_translation_tree.json` for validation and re-import.
- Re-running export preserves existing translations by default.
- Use `--force` only when you intentionally want to rebuild the tree from the supplied PO. It will show a warning and require typing `yes`.

```shell
python3 src/po_json_tree.py \
  --po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po \
  --json files/dsw_root_2.7.0.km \
  --out-dir output/tree \
  --force
```

### Generate PO From Translation Tree

```shell
python3 src/tree_to_po.py \
  --tree-dir output/tree \
  --original-po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po \
  --out-po output/final_translated.po
```

### Check Translation Progress

```shell
python3 src/translation_status.py --tree-dir output/tree
```

This scans the exported tree and reports:

- folders that still contain untranslated fields
- the first `k` untranslated fields in DFS folder order (`k = 5` by default)

### Check Output

```shell
python3 src/po_json_tree.py \
  --po output/final_translated.po \
  --json files/dsw_root_2.7.0.json \
  --report-out output/final_report.json
```

### Optional Final Round-Trip Workflow

```shell
python3 src/translate_workflow.py \
  --po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po \
  --json files/dsw_root_2.7.0.km \
  --tree-dir output/tree \
  --final-po output/final_translated.po \
  --report-out output/final_report.json
```

This is only for a final smoke test or a full round-trip check.
You do not need to run it while translation is still in progress.

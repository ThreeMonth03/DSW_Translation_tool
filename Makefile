PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

PO ?= files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po
MODEL ?= files/dsw_root_2.7.0.km
TREE_DIR ?= output/tree
FINAL_PO ?= output/final_translated.po
REPORT ?= output/final_report.json
TREE_JSON ?= output/tree_snapshot.json
SOURCE_LANG ?= en
TARGET_LANG ?= zh_Hant
STATUS_LIMIT ?= 5
SYNC_GROUP ?= shared-block
SYNC_INTERVAL ?= 10

.PHONY: help install-dev compile lint export-tree export-tree-force status sync sync-watch tree-to-po validate workflow

help:
	@printf '%s\n' \
	'Available targets:' \
	'  install-dev       Install local dev dependencies from config/requirements.txt' \
	'  compile           Run Python syntax compilation checks' \
	'  lint              Run ruff lint checks' \
	'  export-tree       Export PO + model into $(TREE_DIR)' \
	'  export-tree-force Force rebuild $(TREE_DIR) after confirmation' \
	'  status            Show untranslated fields from $(TREE_DIR)' \
	'  sync              Sync shared strings and refresh $(FINAL_PO)' \
	'  sync-watch        Sync every $(SYNC_INTERVAL)s until stopped' \
	'  tree-to-po        Build $(FINAL_PO) from $(TREE_DIR)' \
	'  validate          Validate $(FINAL_PO) against $(MODEL)' \
	'  workflow          Run the optional end-to-end smoke workflow'

install-dev:
	$(PYTHON) -m pip install -r config/requirements.txt

compile:
	$(PYTHON) -m py_compile src/*.py src/dsw_translation_tool/*.py

lint:
	$(PYTHON) -m ruff check --config config/ruff.toml src

export-tree:
	$(PYTHON) src/po_json_tree.py \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

export-tree-force:
	$(PYTHON) src/po_json_tree.py \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--force

status:
	$(PYTHON) src/translation_status.py \
		--tree-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		-k $(STATUS_LIMIT)

sync:
	$(PYTHON) src/sync_shared_strings.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP)

sync-watch:
	$(PYTHON) src/sync_shared_strings.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP) \
		--watch \
		--interval $(SYNC_INTERVAL)

tree-to-po:
	$(PYTHON) src/tree_to_po.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

validate:
	$(PYTHON) src/po_json_tree.py \
		--po $(FINAL_PO) \
		--json $(MODEL) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

workflow:
	$(PYTHON) src/translate_workflow.py \
		--po $(PO) \
		--json $(MODEL) \
		--tree-dir $(TREE_DIR) \
		--final-po $(FINAL_PO) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

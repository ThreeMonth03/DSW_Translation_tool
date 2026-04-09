VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV_PYTHON)
PIP := $(PYTHON) -m pip

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

.PHONY: help venv install-dev compile lint test export-tree export-tree-force status sync sync-watch tree-to-po validate workflow

venv: $(VENV_PYTHON)

$(VENV_PYTHON):
	$(BOOTSTRAP_PYTHON) -m venv $(VENV_DIR)

help:
	@printf '%s\n' \
	'Available targets:' \
	'  venv              Create $(VENV_DIR) when it does not exist' \
	'  install-dev       Install local dev dependencies from config/requirements.txt' \
	'  compile           Run Python syntax compilation checks' \
	'  lint              Run ruff lint checks' \
	'  test              Run pytest test coverage for export/import/sync flows' \
	'  export-tree       Export PO + model into $(TREE_DIR)' \
	'  export-tree-force Force rebuild $(TREE_DIR) after confirmation' \
	'  status            Show untranslated fields from $(TREE_DIR)' \
	'  sync              Sync shared strings and refresh $(FINAL_PO)' \
	'  sync-watch        Sync every $(SYNC_INTERVAL)s until stopped' \
	'  tree-to-po        Build $(FINAL_PO) from $(TREE_DIR)' \
	'  validate          Validate $(FINAL_PO) against $(MODEL)' \
	'  workflow          Run the optional end-to-end smoke workflow'

install-dev: venv
	$(PIP) install -r config/requirements.txt

compile: venv
	$(PYTHON) -m py_compile src/*.py src/dsw_translation_tool/*.py tests/*.py

lint: venv
	$(PYTHON) -m ruff check --config config/ruff.toml src tests

test: venv
	$(PYTHON) -m pytest tests

export-tree: venv
	$(PYTHON) src/po_json_tree.py \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

export-tree-force: venv
	$(PYTHON) src/po_json_tree.py \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--force

status: venv
	$(PYTHON) src/translation_status.py \
		--tree-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		-k $(STATUS_LIMIT)

sync: venv
	$(PYTHON) src/sync_shared_strings.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP)

sync-watch: venv
	$(PYTHON) src/sync_shared_strings.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP) \
		--watch \
		--interval $(SYNC_INTERVAL)

tree-to-po: venv
	$(PYTHON) src/tree_to_po.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

validate: venv
	$(PYTHON) src/po_json_tree.py \
		--po $(FINAL_PO) \
		--json $(MODEL) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

workflow: venv
	$(PYTHON) src/translate_workflow.py \
		--po $(PO) \
		--json $(MODEL) \
		--tree-dir $(TREE_DIR) \
		--final-po $(FINAL_PO) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

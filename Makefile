VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV_PYTHON)
PIP := $(PYTHON) -m pip

PO ?= files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po
MODEL ?= files/dsw_root_2.7.0.km
SOURCE_LANG ?= en
TARGET_LANG ?= zh_Hant
OUTPUT_ROOT ?= translation/$(TARGET_LANG)
TREE_DIR ?= $(OUTPUT_ROOT)/tree
FINAL_PO ?= $(OUTPUT_ROOT)/builds/final_translated.po
REPORT ?= $(OUTPUT_ROOT)/reports/final_report.json
TREE_JSON ?= $(OUTPUT_ROOT)/reports/tree_snapshot.json
REVIEW_DIFF ?= $(OUTPUT_ROOT)/reviews/final_translated.diff
OUTLINE_MD ?= $(TREE_DIR)/outline.md
REVIEW_FLAGS ?=
STATUS_LIMIT ?= 5
SYNC_GROUP ?= shared-block
SYNC_INTERVAL ?= 10

.PHONY: help venv install-dev compile lint test test-infra test-translation export-tree export-tree-force status sync sync-watch tree-to-po review-po validate workflow

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
	'  test              Run all pytest suites' \
	'  test-infra        Run infrastructure/CLI pytest suites' \
	'  test-translation  Run translation consistency pytest suites' \
	'  export-tree       Export PO + model into $(TREE_DIR)' \
	'  export-tree-force Force rebuild $(TREE_DIR) after confirmation' \
	'  status            Show untranslated fields from $(TREE_DIR)' \
	'  sync              Sync shared strings and refresh $(FINAL_PO) + $(REVIEW_DIFF) + $(OUTLINE_MD)' \
	'  sync-watch        Sync every $(SYNC_INTERVAL)s until stopped' \
	'  tree-to-po        Build $(FINAL_PO) from $(TREE_DIR)' \
	'  review-po         Review how $(FINAL_PO) differs from $(PO)' \
	'  validate          Validate $(FINAL_PO) against $(MODEL)' \
	'  workflow          Run the optional end-to-end smoke workflow'

install-dev: venv
	$(PIP) install -r config/requirements.txt

compile: venv
	$(PYTHON) -m compileall -q src tests

lint: venv
	$(PYTHON) -m ruff check --config config/ruff.toml src tests

test: test-infra test-translation

test-infra: venv
	$(PYTHON) -m pytest tests/infra

test-translation: venv
	$(PYTHON) -m pytest tests/translation

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
		--diff-out $(REVIEW_DIFF) \
		--outline-out $(OUTLINE_MD) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP)

sync-watch: venv
	$(PYTHON) src/sync_shared_strings.py \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--diff-out $(REVIEW_DIFF) \
		--outline-out $(OUTLINE_MD) \
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

review-po: venv
	$(PYTHON) src/review_po_changes.py \
		--original-po $(PO) \
		--generated-po $(FINAL_PO) \
		--diff-out $(REVIEW_DIFF) \
		$(REVIEW_FLAGS) \
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

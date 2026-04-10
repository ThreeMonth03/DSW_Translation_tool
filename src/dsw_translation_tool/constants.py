"""Shared constants for DSW translation tooling."""

from __future__ import annotations

import re

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

PO_FIELD_FALLBACKS = {
    "text": ["text", "title", "label", "description", "name", "url"],
    "title": ["title", "text", "label", "description", "name"],
    "label": ["label", "text", "title", "description", "name"],
    "description": ["description", "label", "text", "title", "name"],
    "name": ["name", "title", "text", "label", "description"],
    "url": ["url"],
    "advice": ["advice", "label", "description", "text"],
}

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
PRIMARY_NAME_FIELDS = ("title", "label", "name", "text")
RELATED_NAME_UUID_FIELDS = ("targetUuid", "resourcePageUuid")

MANIFEST_NAME = "_translation_tree.json"
UUID_FILENAME = "_uuid.txt"
TRANSLATION_FILENAME = "translation.md"
TRANSLATION_BACKUP_FILENAME = ".translation.md.bak"
TREE_BACKUP_DIRNAME = "backups"

MAX_SEGMENT_TEXT_LENGTH = 72
FIELD_EXPORT_ORDER = ("title", "label", "text", "advice", "description", "name", "url")

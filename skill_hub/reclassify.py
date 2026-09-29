"""Reclassify retained metadata locally; callers must hold the app's instance lock."""

import json
import sqlite3
from datetime import UTC, datetime

from .db import dump, now


def reclassify_saved(db, classifier):
    """Apply a rules upgrade before starting workers. Never change personal or fetch state."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT k.*, s.repo FROM skills k JOIN sources s ON s.id=k.source_id"
        ).fetchall()
        updates = []
        for row in rows:
            if row["rule_version"] == classifier.version:
                continue
            # Old parser output must still be re-fetched by the next source sync.
            if (row["rule_version"] or "").split(":")[0] != classifier.version.split(":")[0]:
                continue
            previous = json.loads(row["auto_json"])
            if not all(k in previous for k in ("name", "description_original")):
                continue
            data = {**previous, "summary_zh": ""}
            data.update(classifier.classify(row["repo"], row["skill_path"], data))

            def visible(d):
                return {k: v for k, v in d.items() if k != "classification_version"}

            changed_at = now() if visible(previous) != visible(data) else row["changed_at"]
            updates.append((dump(data), classifier.version, changed_at, row["id"]))
        if not updates:
            return {"updated": 0, "backup": None}
        backup_dir = db.path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backup_dir / f"before-classification-{stamp}.sqlite3"
        with sqlite3.connect(backup_path) as backup:
            conn.backup(backup)
        with conn:
            conn.executemany(
                "UPDATE skills SET auto_json=?, rule_version=?, changed_at=? WHERE id=?", updates
            )
        return {"updated": len(updates), "backup": str(backup_path)}

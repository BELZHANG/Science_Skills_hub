import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from skill_hub.classifier import Classifier
from skill_hub.db import dump
from skill_hub.reclassify import reclassify_saved

CASES = json.loads((Path(__file__).parent / "fixtures/classification_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_reviewed_real_world_tasks(case):
    result = Classifier().classify(case["repo"], case["path"], case)
    assert result["primary_category"] == case["expected"]
    assert result["classification_method"] in {"curated", "exact"}
    if case["name"].startswith("setup-") or case["name"] == "career-development":
        assert not result["out_of_scope"]
        assert result["tags"]
        assert not result["review_needed"]


@pytest.mark.parametrize(
    "name,description,expected",
    [
        ("LITERATURE_SEARCH", "Find papers for a systematic review.", "Search"),
        ("literature-review", "Search PubMed and synthesize evidence across studies.", "Reason"),
        ("database-lookup", "Query the database. Not for molecular dynamics simulation.", "Search"),
        ("helper", "Perform document parsing. Do not use for scientific writing.", "Read"),
        ("single_cell_analysis", "Process gene expression matrices.", "Experiment"),
        ("time-series", "Forecast measurements with ARIMA.", "Experiment"),
        ("helper", "Perform thematic analysis of interview transcripts.", "Experiment"),
        ("helper", "Manage reference management libraries in Zotero.", "Write"),
        ("helper", "Run code for arbitrary tasks.", None),
    ],
)
def test_fallback_primary_intent_and_normalization(name, description, expected):
    result = Classifier().classify(
        "new/repo",
        "skills/example/SKILL.md",
        {
            "name": name,
            "description_original": description,
        },
    )
    assert result["primary_category"] == expected
    if name == "LITERATURE_SEARCH":
        assert result["review_needed"] is False


def test_changed_description_and_source_cannot_reuse_catalog():
    case = next(c for c in CASES if c["name"] == "pdf" and c["repo"] == "anthropics/skills")
    changed = {**case, "description_original": "scientific writing"}
    result = Classifier().classify(case["repo"], case["path"], changed)
    assert result["classification_method"] == "keywords"
    assert result["primary_category"] == "Write"
    assert result["review_needed"]
    assert "已变化" in result["classification_reason"]
    other = Classifier().classify("other/repo", case["path"], changed)
    assert other["classification_method"] == "keywords"
    assert "已变化" not in other["classification_reason"]


def test_incomplete_metadata_stays_flagged():
    case = CASES[0]
    result = Classifier().classify(case["repo"], case["path"], {**case, "warnings": ["缺少介绍"]})
    assert result["review_needed"]


def test_catalog_change_invalidates_rule_version(tmp_path):
    config = {"categories": {}, "domains": {}, "out_of_scope": [], "catalog_file": "catalog.yaml"}
    rules = tmp_path / "rules.yaml"
    rules.write_text(yaml.safe_dump(config))
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("groups: []\n")
    previous = Classifier(rules).version
    catalog.write_text("# changed\ngroups: []\n")
    assert Classifier(rules).version != previous


def test_upgrade_preserves_personal_and_fetch_state_and_is_idempotent(db):
    classifier = Classifier()
    old_version = classifier.version.split(":")[0] + ":previous"
    auto = dict(
        name="single-cell",
        description_original="Analyze expression matrices.",
        primary_category=None,
        summary_zh="",
        warnings=["incomplete metadata"],
    )
    db.write(
        """INSERT INTO skills(source_id, skill_path, auto_json, file_sha, rule_version,
        parse_status, first_seen_at, last_seen_at, changed_at, missing, favorite, featured,
        user_overrides_json, notes, evidence_json) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "skills/test/SKILL.md",
            dump(auto),
            "original-sha",
            old_version,
            "incomplete",
            "first",
            "last",
            "changed",
            1,
            1,
            1,
            dump({"primary_category": "Write", "summary_zh": "我的简介", "tags": ["自定义"]}),
            "我的笔记",
            '[{"note":"my evidence"}]',
        ),
    )
    before = db.one("SELECT * FROM skills")
    report = reclassify_saved(db, classifier)
    after = db.one("SELECT * FROM skills")
    assert report["updated"] == 1
    with sqlite3.connect(report["backup"]) as backup:
        assert backup.execute("SELECT auto_json FROM skills").fetchone()[0] == before["auto_json"]
    protected = set(before) - {"auto_json", "rule_version", "changed_at"}
    assert {k: before[k] for k in protected} == {k: after[k] for k in protected}
    assert json.loads(after["auto_json"])["primary_category"] == "Experiment"
    assert json.loads(after["auto_json"])["review_needed"]
    assert db.skills()[0]["primary_category"] == "Write"
    assert reclassify_saved(db, classifier) == {"updated": 0, "backup": None}
    assert db.one("SELECT * FROM skills") == after


def test_parser_upgrade_not_masked(db):
    db.write(
        """INSERT INTO skills(source_id,skill_path,auto_json,rule_version,parse_status,
        first_seen_at,last_seen_at,changed_at) VALUES(1,'x',?,'obsolete:rules','success','a','b','c')""",
        (dump({"name": "test", "description_original": "statistical analysis"}),),
    )
    assert reclassify_saved(db, Classifier())["updated"] == 0
    assert db.one("SELECT rule_version FROM skills")["rule_version"] == "obsolete:rules"

import pytest

from skill_hub.classifier import Classifier
from skill_hub.parser import MAX_DOCUMENT, parse


def test_unicode_bom_multiline():
    result = parse(
        "\ufeff---\nname: 科研\ndescription: |\n  第一行\n  第二行\n---\n# Body",
        "skills/a/SKILL.md",
    )
    assert result["name"] == "科研"
    assert result["description_original"] == "第一行\n第二行"
    assert result["warnings"] == []
    assert result["api_key_status"] == result["paid_status"] == "unknown"


@pytest.mark.parametrize(
    "body",
    [
        "",
        "# Fallback\nSome text",
        "---\nname: [broken\n---\n# Name",
        "---\na: &a [*a]\n---\n# Safe",
        '---\nx: !!python/object/apply:os.system ["false"]\n---\n# Safe',
    ],
)
def test_bad_metadata_is_safe(body):
    result = parse(body, "skills/fallback/SKILL.md")
    assert result["name"]
    assert result["warnings"]


def test_size_limit():
    with pytest.raises(ValueError):
        parse("x" * (MAX_DOCUMENT + 1), "skills/a/SKILL.md")


@pytest.mark.parametrize(
    "phrase,category",
    [
        ("文献检索", "Search"),
        ("literature search", "Search"),
        ("document parsing", "Read"),
        ("方法学批判", "Reason"),
        ("critical thinking", "Reason"),
        ("hypothesis generation", "Reason"),
        ("statistical analysis", "Experiment"),
        ("scientific visualization", "Experiment"),
        ("scientific writing", "Write"),
        ("citation management", "Write"),
        ("literature review", "Reason"),
    ],
)
def test_concept_mapping(phrase, category):
    assert (
        Classifier().classify(
            "test/research",
            "fixture/SKILL.md",
            {"name": "test-fixture", "description_original": phrase},
        )["primary_category"]
        == category
    )


def test_unknown_and_no_code_bias():
    result = Classifier().classify(
        "test/research", "x/SKILL.md", {"name": "python-helper", "description_original": "Run code"}
    )
    assert result["primary_category"] is None
    assert result["review_needed"]


def test_scope_and_exact_isolation(tmp_path):
    file = tmp_path / "rules.yaml"
    file.write_text(
        "version: 1\ncategories: {}\ndomains: {}\nout_of_scope: []\nexact:\n  - repo: trusted/repo\n    name: same-name\n    values: {primary_category: Read}\n"
    )
    c = Classifier(file)
    data = {"name": "same-name", "description_original": "Anything"}
    assert c.classify("trusted/repo", "a/SKILL.md", data)["primary_category"] == "Read"
    assert c.classify("other/repo", "a/SKILL.md", data)["primary_category"] is None

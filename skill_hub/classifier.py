import hashlib
import re
from pathlib import Path

import yaml

from .config import CONFIG_DIR
from .parser import PARSER_VERSION

ALGORITHM_VERSION = "3"


class Classifier:
    def __init__(self, path=None):
        path = Path(path) if path else CONFIG_DIR / "classification_rules.yaml"
        raw = path.read_bytes()
        self.rules = yaml.safe_load(raw)
        self.catalog = {}
        catalog_raw = b""
        if self.rules.get("catalog_file"):
            catalog_raw = (path.parent / self.rules["catalog_file"]).read_bytes()
            for group in yaml.safe_load(catalog_raw)["groups"]:
                for item_path, fingerprint in group["items"].items():
                    key = (group["repo"].casefold(), item_path)
                    if key in self.catalog:
                        raise ValueError(f"重复分类映射: {key}")
                    self.catalog[key] = (fingerprint, group)
        digest = hashlib.sha256(ALGORITHM_VERSION.encode() + raw + catalog_raw).hexdigest()[:16]
        # 保留解析器版本前缀，分类变化仍可复用已有原始介绍。
        self.version = PARSER_VERSION + ":" + digest

    @staticmethod
    def normalize(text):
        return re.sub(r"\s+", " ", re.sub(r"[-_–—]+", " ", text.casefold())).strip()

    @classmethod
    def matches(cls, phrase, text):
        phrase, text = cls.normalize(phrase), cls.normalize(text)
        if phrase.isascii():
            return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))
        return phrase in text

    @staticmethod
    def fingerprint(data):
        text = data["name"] + "\n" + data["description_original"]
        return hashlib.sha256(text.encode()).hexdigest()[:20]

    def classify(self, repo, path, data):
        name = self.normalize(data["name"])
        # 不用“不要用于…”里的任务词作为正向分类证据。
        clauses = re.split(r"(?<=[.!?。；;])\s*|\n+", data["description_original"])
        positive = [
            re.split(
                r"\b(?:do not use|don.t use|not for|never use|instead use)\b|不要用于|不适用于",
                clause,
                maxsplit=1,
                flags=re.I,
            )[0]
            for clause in clauses
        ]
        lead = self.normalize(positive[0] if positive else "")
        body = self.normalize(" ".join(positive))
        text = name + " " + body
        hits, scores, category_tags = {}, {}, {}
        for category, groups in self.rules["categories"].items():
            for tag, phrases in groups.items():
                matched = []
                weights = []
                for phrase in phrases:
                    weight = (
                        8
                        if self.matches(phrase, name)
                        else 4
                        if self.matches(phrase, lead)
                        else 1
                        if self.matches(phrase, body)
                        else 0
                    )
                    if weight:
                        matched.append(phrase)
                        weights.append(weight)
                if matched:
                    hits.setdefault(category, []).extend(matched)
                    # 同义词不重复堆分；名称/首句的主任务优先于长介绍中的附带用途。
                    scores[category] = max(scores.get(category, 0), max(weights))
                    category_tags.setdefault(category, []).append(tag)
        ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
        primary = ranked[0] if ranked else None
        secondary = [k for k in ranked[1:] if scores[k] >= 4][:3]
        review = not primary or (len(ranked) > 1 and scores[ranked[0]] == scores[ranked[1]])
        result = {
            "primary_category": primary,
            "secondary_categories": secondary,
            "tags": list(
                dict.fromkeys(t for k in [primary, *secondary] for t in category_tags.get(k, []))
            ),
            "domain": next(
                (
                    d
                    for d, ps in self.rules["domains"].items()
                    if any(self.matches(p, text) for p in ps)
                ),
                "",
            ),
            "review_needed": review,
            "out_of_scope": not primary
            and any(self.matches(p, text) for p in self.rules["out_of_scope"]),
            "classification_method": "keywords" if hits else "unclassified",
            "classification_reason": "；".join(
                f"{k}（任务权重 {scores[k]}）: {', '.join(v)}" for k, v in hits.items()
            )
            or "缺少明确科研任务证据，保留未分类供复核",
            "classification_version": self.version,
        }
        catalog = self.catalog.get((repo.casefold(), path))
        stale = False
        if catalog:
            fingerprint, group = catalog
            if fingerprint == self.fingerprint(data):
                result.update(group["values"])
                result.update(
                    classification_method="curated", classification_reason=group["reason"]
                )
            else:
                stale = True
        # 保留已有来源限定的中文简介；已变化的介绍不能继续套用旧的映射。
        if not stale:
            for rule in self.rules.get("exact", []):
                if rule["repo"].casefold() == repo.casefold() and (
                    rule.get("path") == path or rule.get("name") == data["name"]
                ):
                    result.update(rule["values"])
                    result.update(
                        classification_method="exact", classification_reason="已核对的来源限定映射"
                    )
                    break
        if stale:
            result["review_needed"] = True
            result["classification_reason"] = (
                "原始介绍已变化，原映射待复核；" + result["classification_reason"]
            )
        if data.get("warnings"):
            result["review_needed"] = True
        # 防止外部调用修改共享规则中的列表。
        result["tags"] = list(result["tags"])
        result["secondary_categories"] = list(result["secondary_categories"])
        return result

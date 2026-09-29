import re
from pathlib import PurePosixPath

import yaml
from yaml.tokens import AliasToken, AnchorToken

MAX_DOCUMENT = 256 * 1024
PARSER_VERSION = "1"


def bounded_yaml(text):
    if len(text.encode()) > MAX_DOCUMENT:
        raise ValueError("YAML 超出大小限制")
    # No alias expansion or recursive structures in untrusted metadata.
    depth = 0
    for count, token in enumerate(yaml.scan(text)):
        if count > 10000 or isinstance(token, (AliasToken, AnchorToken)):
            raise ValueError("YAML 过于复杂或包含别名")
        name = type(token).__name__
        if name in {
            "BlockMappingStartToken",
            "BlockSequenceStartToken",
            "FlowMappingStartToken",
            "FlowSequenceStartToken",
        }:
            depth += 1
        elif name in {"BlockEndToken", "FlowMappingEndToken", "FlowSequenceEndToken"}:
            depth -= 1
        if depth > 20:
            raise ValueError("YAML 嵌套过深")
    return yaml.safe_load(text)


def parse(text, path):
    if len(text.encode()) > MAX_DOCUMENT:
        raise ValueError("介绍文档超过 256 KiB，未处理")
    text = text.lstrip("\ufeff")
    body, meta, warnings = text, {}, []
    if text.startswith("---\n") or text.startswith("---\r\n"):
        parts = re.split(r"(?m)^---\s*$", text, maxsplit=2)
        if len(parts) == 3:
            try:
                loaded = bounded_yaml(parts[1])
                if not isinstance(loaded, dict):
                    raise ValueError("frontmatter 必须是映射")
                meta = loaded
            except (yaml.YAMLError, ValueError, RecursionError):
                warnings.append("frontmatter 无效或不安全，已使用显示兜底")
            body = parts[2]
        else:
            warnings.append("frontmatter 未闭合")
    else:
        warnings.append("缺少 YAML frontmatter")

    def scalar(key, limit):
        v = meta.get(key)
        return v.strip()[:limit] if isinstance(v, str) else ""

    heading = re.search(r"(?m)^#{1,3}\s+(.+)$", body)
    name = scalar("name", 200)
    description = scalar("description", 6000)
    if not name:
        name = (heading.group(1) if heading else PurePosixPath(path).parent.name)[:200]
        warnings.append("缺少 name")
    if not description:
        description = re.sub(r"\s+", " ", re.sub(r"(?m)^#+.*$", "", body)).strip()[:600]
        warnings.append("缺少 description；介绍为正文短摘录")
    compatibility = scalar("compatibility", 2000)
    # Preserve short author statements without inferring absence of requirements.
    lines = [
        line.strip()
        for line in body.splitlines()
        if re.search(
            r"api.?key|requires? |prerequisite|subscription|paid |付费|密钥|需要", line, re.I
        )
    ]
    excerpt = "\n".join(lines[:4])[:1200]
    return {
        "name": name,
        "description_original": description,
        "license": scalar("license", 500),
        "compatibility": compatibility,
        "requirements_note": compatibility or "未确认",
        "requirements_excerpt": excerpt,
        "api_key_status": "unknown",
        "paid_status": "unknown",
        "warnings": warnings,
        "summary_zh": "",
        "links": [],
    }

import json
import math
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import CATEGORIES, ROOT, STATES, normalize_repo, safe_link, validate_path
from .db import dump

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "templates")
templates.env.filters["safe_link"] = safe_link
LABELS = {"Search": "检索", "Read": "阅读", "Reason": "推理", "Experiment": "实验", "Write": "写作"}
STATUS = {
    "queued": "排队中",
    "running": "更新中",
    "success": "完成",
    "partial": "部分完成",
    "failed": "失败",
    "interrupted": "未完成",
    None: "尚未刷新",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(StrictModel):
    url: str = Field(max_length=2000)
    type: Literal["官方演示", "作者报告", "第三方案例", "待核实"] = "待核实"

    @field_validator("url")
    @classmethod
    def valid_url(cls, v):
        if not safe_link(v):
            raise ValueError("链接仅支持无凭据的 http/https URL")
        return v


class SourceInput(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    repo: str = Field(max_length=250)
    scan_roots: list[str] = Field(default_factory=list, max_length=20)
    explicit_paths: list[str] = Field(default_factory=list, max_length=30)
    branch: str = Field(default="", max_length=200)
    enabled: bool = True
    refresh_interval_hours: Literal[0, 24, 168] = 24
    notes: str = Field(default="", max_length=3000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)

    @field_validator("repo")
    @classmethod
    def repo_valid(cls, v):
        return normalize_repo(v)

    @field_validator("scan_roots", "explicit_paths")
    @classmethod
    def paths_valid(cls, v, info):
        return list(dict.fromkeys(validate_path(p, info.field_name == "explicit_paths") for p in v))

    @field_validator("branch")
    @classmethod
    def branch_valid(cls, v):
        if any(ord(c) < 32 for c in v) or ".." in v:
            raise ValueError("分支名称无效")
        return v.strip()


OVERRIDE_KEYS = {
    "primary_category",
    "secondary_categories",
    "summary_zh",
    "tags",
    "domain",
    "requirements_note",
    "api_key_status",
    "paid_status",
    "out_of_scope",
}


class SkillPatch(StrictModel):
    favorite: bool | None = None
    featured: bool | None = None
    notes: str | None = Field(default=None, max_length=6000)
    overrides: dict = Field(default_factory=dict)
    clear_overrides: list[str] = Field(default_factory=list)
    evidence: list[Evidence] | None = Field(default=None, max_length=20)

    @field_validator("clear_overrides")
    @classmethod
    def clear_valid(cls, v):
        if set(v) - OVERRIDE_KEYS:
            raise ValueError("未知的覆盖字段")
        return v

    @field_validator("overrides")
    @classmethod
    def override_valid(cls, v):
        if set(v) - OVERRIDE_KEYS:
            raise ValueError("只允许修改人工字段")
        for k, value in v.items():
            if k == "primary_category":
                valid = value is None or value in CATEGORIES
            elif k in {"secondary_categories", "tags"}:
                valid = (
                    isinstance(value, list)
                    and len(value) <= 30
                    and all(isinstance(x, str) and len(x) <= 100 for x in value)
                )
                if k == "secondary_categories" and valid:
                    valid = all(x in CATEGORIES for x in value)
            elif k in {"api_key_status", "paid_status"}:
                valid = isinstance(value, str) and value in STATES
            elif k == "out_of_scope":
                valid = isinstance(value, bool)
            else:
                valid = isinstance(value, str) and len(value) <= 6000
            if not valid:
                raise ValueError(f"覆盖字段 {k} 的值无效")
        return v


class Refresh(StrictModel):
    source_id: int | None = None


def public_source(s):
    return (
        {
            k: v
            for k, v in s.items()
            if k not in {"cache_json", "config_json", "last_scope", "evidence_json"}
        }
        | json.loads(s["config_json"])
        | {"evidence": json.loads(s["evidence_json"]), "enabled": bool(s["enabled"])}
    )


def listing(
    db,
    q="",
    category="",
    source="",
    domain="",
    favorite=False,
    featured=False,
    show_disabled=False,
    sort="name",
    page=1,
    page_size=24,
):
    all_items = db.skills()
    items = []
    for s in all_items:
        if not show_disabled and not s["source_enabled"]:
            continue
        if category == "out":
            if not s.get("out_of_scope"):
                continue
        elif s.get("out_of_scope"):
            continue
        if category == "unclassified" and s.get("primary_category"):
            continue
        if category in CATEGORIES and category != s.get("primary_category"):
            continue
        if source and str(s["source_id"]) != str(source):
            continue
        if domain and s.get("domain") != domain:
            continue
        if favorite and not s["favorite"] or featured and not s["featured"]:
            continue
        haystack = " ".join(
            [
                s.get("name", ""),
                s.get("description_original", ""),
                s.get("summary_zh", ""),
                " ".join(s.get("tags", [])),
            ]
        ).casefold()
        if not all(word in haystack for word in q.casefold().split()):
            continue
        items.append(s)
    if sort == "stars":
        items.sort(
            key=lambda s: (s["stars"] is None, -(s["stars"] or 0), s.get("name", "").casefold())
        )
    elif sort in {"first_seen_at", "changed_at"}:
        items.sort(key=lambda s: s[sort], reverse=True)
    else:
        items.sort(key=lambda s: s.get("name", "").casefold())
    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    page = min(max(1, page), pages)
    return {
        "items": items[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "pages": pages,
        "page_size": page_size,
        "domains": sorted({s.get("domain") for s in all_items if s.get("domain")}),
    }


@router.get("/api/skills")
async def skills(
    request: Request,
    q: str = Query("", max_length=300),
    category: str = "",
    source: str = "",
    domain: str = "",
    favorite: bool = False,
    featured: bool = False,
    show_disabled: bool = False,
    sort: str = "name",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    return listing(
        request.app.state.db,
        q,
        category,
        source,
        domain,
        favorite,
        featured,
        show_disabled,
        sort,
        page,
        page_size,
    )


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    params = dict(request.query_params)

    def number(k, default, maximum):
        try:
            return min(maximum, max(1, int(params.get(k, default))))
        except ValueError:
            return default

    result = listing(
        request.app.state.db,
        **{k: params.get(k, "") for k in ["q", "category", "source", "domain"]},
        **{
            k: params.get(k) in {"1", "true", "on"}
            for k in ["favorite", "featured", "show_disabled"]
        },
        sort=params.get("sort", "name"),
        page=number("page", 1, 100000),
        page_size=24,
    )

    def link(**changes):
        from urllib.parse import urlencode

        return "/?" + urlencode(params | changes)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            **result,
            "params": params,
            "sources": request.app.state.db.sources(),
            "labels": LABELS,
            "categories": CATEGORIES,
            "link": link,
            "csrf": request.app.state.csrf,
            "status_labels": STATUS,
        },
    )


@router.get("/sources", response_class=HTMLResponse)
async def source_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="sources.html",
        context={
            "sources": [public_source(s) for s in request.app.state.db.sources()],
            "csrf": request.app.state.csrf,
            "status_labels": STATUS,
            "has_token": bool(request.app.state.settings.token),
        },
    )


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/api/skills/{skill_id}")
async def detail(request: Request, skill_id: int):
    item = next((s for s in request.app.state.db.skills() if s["id"] == skill_id), None)
    if not item:
        raise HTTPException(404, "条目不存在")
    return item


@router.patch("/api/skills/{skill_id}")
async def edit_skill(request: Request, skill_id: int, patch: SkillPatch):
    db = request.app.state.db
    row = db.one("SELECT * FROM skills WHERE id=?", (skill_id,))
    if not row:
        raise HTTPException(404, "条目不存在")
    overrides = json.loads(row["user_overrides_json"])
    for k in patch.clear_overrides:
        overrides.pop(k, None)
    overrides.update(patch.overrides)
    db.write(
        """UPDATE skills SET favorite=?,featured=?,notes=?,user_overrides_json=?,evidence_json=? WHERE id=?""",
        (
            patch.favorite if patch.favorite is not None else row["favorite"],
            patch.featured if patch.featured is not None else row["featured"],
            patch.notes if patch.notes is not None else row["notes"],
            dump(overrides),
            dump([e.model_dump() for e in patch.evidence])
            if patch.evidence is not None
            else row["evidence_json"],
            skill_id,
        ),
    )
    return await detail(request, skill_id)


@router.get("/api/sources")
async def sources(request: Request):
    return [public_source(s) for s in request.app.state.db.sources()]


async def save_source(request, source, source_id=None):
    if not source.scan_roots and not source.explicit_paths:
        raise HTTPException(422, "至少配置一个扫描目录或精确文件")
    db = request.app.state.db
    old = db.one("SELECT * FROM sources WHERE id=?", (source_id,)) if source_id else None
    if source_id and not old:
        raise HTTPException(404, "来源不存在")
    if old and old["repo"] != source.repo:
        raise HTTPException(422, "仓库身份不可更改，请添加新来源并停用旧来源")
    config = dump(
        {
            "scan_roots": source.scan_roots,
            "explicit_paths": source.explicit_paths,
            "branch": source.branch,
        }
    )
    args = (
        source.name,
        source.repo,
        config,
        source.enabled,
        source.refresh_interval_hours,
        source.notes,
        dump([e.model_dump() for e in source.evidence]),
    )
    try:
        if old:
            db.write(
                """UPDATE sources SET name=?,repo=?,config_json=?,enabled=?,refresh_interval_hours=?,notes=?,evidence_json=?,
                next_due_at=CASE WHEN config_json!=? OR refresh_interval_hours!=? OR enabled!=? THEN NULL ELSE next_due_at END WHERE id=?""",
                (*args, config, source.refresh_interval_hours, source.enabled, source_id),
            )
        else:
            source_id = db.write(
                """INSERT INTO sources(name,repo,config_json,enabled,refresh_interval_hours,notes,evidence_json)
                VALUES(?,?,?,?,?,?,?)""",
                args,
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "该仓库已存在，请编辑现有来源") from None
    return {"id": source_id}


@router.post("/api/sources", status_code=201)
async def add_source(request: Request, source: SourceInput):
    return await save_source(request, source)


@router.patch("/api/sources/{source_id}")
async def edit_source(request: Request, source_id: int):
    db = request.app.state.db
    row = next((public_source(s) for s in db.sources() if s["id"] == source_id), None)
    if not row:
        raise HTTPException(404, "来源不存在")
    body = await request.json()
    if not isinstance(body, dict) or set(body) - set(SourceInput.model_fields):
        raise HTTPException(422, "未知来源字段")
    from pydantic import ValidationError

    try:
        source = SourceInput.model_validate({k: row[k] for k in SourceInput.model_fields} | body)
    except ValidationError:
        raise HTTPException(422, "来源字段格式无效，请检查路径与周期") from None
    return await save_source(request, source, source_id)


@router.post("/api/refresh")
async def refresh(request: Request, body: Refresh):
    db, service = request.app.state.db, request.app.state.service
    ids = (
        [body.source_id]
        if body.source_id is not None
        else [s["id"] for s in db.sources() if s["enabled"]]
    )
    tasks, deferred = [], []
    for source_id in ids:
        try:
            tasks.append(service.enqueue(source_id))
        except ValueError as e:
            deferred.append({"source_id": source_id, "reason": str(e)})
    return {"task_ids": tasks, "deferred": deferred}


@router.get("/api/sync-runs")
async def runs(request: Request, ids: str = Query("", max_length=1000)):
    rows = request.app.state.db.read("""SELECT r.*,s.name AS source_name FROM sync_runs r
        JOIN sources s ON s.id=r.source_id ORDER BY r.id DESC LIMIT 100""")
    if ids:
        rows = [r for r in rows if str(r["id"]) in ids.split(",")]
    return rows

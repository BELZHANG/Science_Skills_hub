import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit

import httpx

from .parser import MAX_DOCUMENT

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
IGNORED = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "__fixtures__",
    "__tests__",
    "skill_template",
    "skill-template",
}


class FetchError(Exception):
    def __init__(self, message, retry_at=None):
        super().__init__(message)
        self.retry_at = retry_at


class GitHub:
    def __init__(self, client, token="", sleep=asyncio.sleep):
        self.client, self.token, self.sleep = client, token, sleep

    async def request(self, url, etag=None, limit=8 * 1024 * 1024):
        u = urlsplit(url)
        if u.scheme != "https" or u.netloc not in {"api.github.com", "raw.githubusercontent.com"}:
            raise FetchError("拒绝非白名单 GitHub 主机")
        headers = {"User-Agent": "Research-Skill-Hub/0.1", "Accept": "application/vnd.github+json"}
        if u.netloc == "api.github.com":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        if etag:
            headers["If-None-Match"] = etag
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET", url, headers=headers, follow_redirects=False
                ) as response:
                    status = response.status_code
                    content = bytearray()
                    async for part in response.aiter_bytes():
                        content.extend(part)
                        if len(content) > limit:
                            raise FetchError("响应超过大小限制，未处理")
                    h = response.headers
                    if status == 304:
                        return None, h.get("etag") or etag
                    # Redirects are deliberately refused; user can correct renamed repository.
                    if 300 <= status < 400:
                        raise FetchError("GitHub 返回重定向，请检查仓库是否改名并修正来源")
                    rate_limited = status == 429 or (
                        status == 403
                        and (
                            h.get("x-ratelimit-remaining") == "0"
                            or "retry-after" in h
                            or b"rate limit" in bytes(content).lower()
                        )
                    )
                    if rate_limited:
                        deadline = datetime.now(UTC) + timedelta(minutes=15)
                        if h.get("retry-after"):
                            try:
                                deadline = datetime.now(UTC) + timedelta(
                                    seconds=max(1, int(h["retry-after"]))
                                )
                            except ValueError:
                                try:
                                    deadline = parsedate_to_datetime(h["retry-after"]).astimezone(
                                        UTC
                                    )
                                except (ValueError, TypeError):
                                    pass
                        elif h.get("x-ratelimit-reset", "").isdigit():
                            deadline = datetime.fromtimestamp(int(h["x-ratelimit-reset"]) + 2, UTC)
                        raise FetchError("GitHub 限流，已延后重试", deadline.isoformat())
                    if status >= 500:
                        if attempt < 2:
                            await self.sleep(0.5 * 2**attempt)
                            continue
                        raise FetchError(f"GitHub 服务错误 HTTP {status}")
                    if status == 404:
                        raise FetchError("GitHub 404：仓库、分支或扫描路径不存在，或不可公开访问")
                    if status in {401, 403}:
                        raise FetchError(f"GitHub 认证或访问权限错误 HTTP {status}")
                    if status != 200:
                        raise FetchError(f"GitHub 请求失败 HTTP {status}")
                    return bytes(content), h.get("etag")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt < 2:
                    await self.sleep(0.5 * 2**attempt)
                    continue
                raise FetchError("网络连接失败或超时，已保留现有数据") from None

    async def json(self, url):
        raw, _ = await self.request(url)
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            raise FetchError("GitHub 返回无效 JSON") from None

    async def metadata(self, repo, cache):
        raw, etag = await self.request(f"{API}/repos/{repo}", cache.get("etag"))
        if raw is None and not cache.get("data"):
            raw, etag = await self.request(f"{API}/repos/{repo}")
        if raw is None:
            if not cache.get("data"):
                raise FetchError("304 响应缺少可复用缓存")
            meta = cache["data"]
        else:
            try:
                full = json.loads(raw)
                meta = {
                    k: full.get(k)
                    for k in [
                        "id",
                        "private",
                        "default_branch",
                        "stargazers_count",
                        "forks_count",
                        "archived",
                        "pushed_at",
                        "license",
                    ]
                }
            except (ValueError, TypeError):
                raise FetchError("仓库元数据无效") from None
        if meta.get("private") is not False:
            raise FetchError("仅支持公开仓库")
        return meta, {"etag": etag, "data": meta}

    async def snapshot(self, repo, branch):
        commit = await self.json(f"{API}/repos/{repo}/commits/{quote(branch, safe='')}")
        sha, tree = commit.get("sha", ""), commit.get("commit", {}).get("tree", {}).get("sha", "")
        if not re.fullmatch(r"[a-f0-9]{40,64}", sha) or not re.fullmatch(r"[a-f0-9]{40,64}", tree):
            raise FetchError("无法确认固定 commit 快照")
        return sha, tree

    async def discover(self, repo, tree_sha, config):
        """Resolve only configured paths, recursively fetch each selected subtree.

        If GitHub truncates a recursive response, walk non-recursive subtrees.
        Never interpret incomplete enumeration as a deletion.
        """
        cache, found, errors = {}, {}, []
        requests = 0

        async def tree(sha, recursive=False):
            nonlocal requests
            key = (sha, recursive)
            if key not in cache:
                requests += 1
                if requests > 300:
                    raise FetchError("目录枚举超过单次 300 个树请求上限")
                suffix = "?recursive=1" if recursive else ""
                cache[key] = await self.json(f"{API}/repos/{repo}/git/trees/{sha}{suffix}")
            return cache[key]

        def usable(path):
            return not any(p.lower() in IGNORED for p in path.split("/"))

        def add(prefix, entry):
            p = "/".join(filter(None, [prefix, entry["path"]]))
            if (
                entry.get("type") == "blob"
                and entry.get("mode") in {"100644", "100755"}
                and p.endswith("/SKILL.md")
                and usable(p)
            ):
                found[p] = entry["sha"]
            elif p == "SKILL.md" and entry.get("mode") in {"100644", "100755"}:
                found[p] = entry["sha"]

        async def resolve(path):
            current = tree_sha
            parts = path.split("/")
            for index, part in enumerate(parts):
                data = await tree(current)
                if data.get("truncated"):
                    raise FetchError(f"路径 {path} 的父目录被截断")
                entry = next((e for e in data["tree"] if e["path"] == part), None)
                if not entry:
                    raise FetchError(f"扫描路径未找到：{path}，请检查来源设置")
                if index < len(parts) - 1:
                    if entry.get("type") != "tree":
                        raise FetchError(f"扫描路径不是目录：{path}")
                    current = entry["sha"]
            return entry

        async def walk(prefix, sha, depth=0):
            if depth > 30:
                raise FetchError("目录超过最大遍历深度")
            data = await tree(sha, True)
            if not data.get("truncated"):
                for entry in data["tree"]:
                    add(prefix, entry)
                return
            data = await tree(sha)
            if data.get("truncated"):
                errors.append(f"目录结果截断：{prefix}")
            for entry in data["tree"]:
                add(prefix, entry)
                path = f"{prefix}/{entry['path']}"
                if entry.get("type") == "tree" and usable(path):
                    await walk(path, entry["sha"], depth + 1)

        for root in config["scan_roots"]:
            if not usable(root):
                continue
            try:
                entry = await resolve(root)
                if entry.get("type") != "tree":
                    raise FetchError(f"扫描根不是目录：{root}")
                await walk(root, entry["sha"])
            except FetchError as e:
                if e.retry_at:
                    raise
                errors.append(str(e))
        for path in config["explicit_paths"]:
            if not usable(path):
                continue
            try:
                entry = await resolve(path)
                add(path.rsplit("/", 1)[0] if "/" in path else "", entry)
                if path not in found:
                    raise FetchError(f"路径不是可读取的普通 Skill 文件：{path}")
            except FetchError as e:
                if e.retry_at:
                    raise
                errors.append(str(e))
        return found, errors

    async def document(self, repo, commit, path):
        url = f"{RAW}/{repo}/{quote(commit, safe='')}/{quote(path, safe='/')}"
        raw, _ = await self.request(url, limit=MAX_DOCUMENT)
        try:
            return raw.decode("utf-8-sig")
        except (UnicodeError, AttributeError):
            raise FetchError("文档不是有效 UTF-8") from None

import httpx
import pytest
from conftest import BLOB, COMMIT, SUBTREE, TREE, no_wait

from skill_hub.github_source import FetchError, GitHub


@pytest.mark.parametrize(
    "status,headers,body,rate",
    [
        (403, {}, "Forbidden", False),
        (401, {}, "", False),
        (404, {}, "", False),
        (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"}, "", True),
        (429, {"retry-after": "10"}, "", True),
        (403, {}, "secondary rate limit", True),
    ],
)
async def test_error_types(status, headers, body, rate):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, headers=headers, text=body))
    ) as client:
        with pytest.raises(FetchError) as exc:
            await GitHub(client).request("https://api.github.com/repos/test/repo")
        assert bool(exc.value.retry_at) == rate


async def test_304_without_cache_and_token_scope():
    calls = []

    def handler(r):
        calls.append(r)
        if "if-none-match" in r.headers:
            return httpx.Response(304)
        if r.url.host == "raw.githubusercontent.com":
            assert "authorization" not in r.headers
            return httpx.Response(200, text="body")
        assert r.headers["authorization"] == "Bearer test-only-fake-token"
        return httpx.Response(200, json={"id": 1, "private": False, "default_branch": "main"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        g = GitHub(client, "test-only-fake-token")
        meta, cache = await g.metadata("test/repo", {"etag": "old"})
        assert meta["id"] == 1
        assert len(calls) == 2
        await g.document("test/repo", COMMIT, "a/SKILL.md")
        with pytest.raises(FetchError):
            await g.request("https://localhost/secrets")


async def test_retry_bounded_timeout_and_redirect():
    calls = []

    def handler(r):
        calls.append(r)
        raise httpx.ReadTimeout("fixture", request=r)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FetchError):
            await GitHub(client, sleep=no_wait).request("https://api.github.com/repos/test/repo")
        assert len(calls) == 3
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "http://localhost/secret"})
        )
    ) as client:
        with pytest.raises(FetchError, match="重定向"):
            await GitHub(client).request("https://api.github.com/repos/test/repo")


async def test_truncated_recursive_recovers_and_ignores_links():
    deep = "e" * 40

    def handler(r):
        sha = r.url.path.split("/")[-1]
        if sha == TREE:
            entries = [{"path": "skills", "type": "tree", "mode": "040000", "sha": SUBTREE}]
        elif sha == SUBTREE and r.url.query:
            return httpx.Response(200, json={"tree": [], "truncated": True})
        elif sha == SUBTREE:
            entries = [
                {"path": "SKILL.md", "type": "blob", "mode": "100644", "sha": BLOB},
                {"path": "nested", "type": "tree", "mode": "040000", "sha": deep},
                {"path": "link/SKILL.md", "type": "blob", "mode": "120000", "sha": BLOB},
            ]
        else:
            entries = [
                {"path": "SKILL.md", "type": "blob", "mode": "100644", "sha": BLOB},
                {"path": "skill_template/SKILL.md", "type": "blob", "mode": "100644", "sha": BLOB},
            ]
        return httpx.Response(200, json={"tree": entries, "truncated": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found, errors = await GitHub(client).discover(
            "test/repo", TREE, {"scan_roots": ["skills"], "explicit_paths": ["skills/SKILL.md"]}
        )
        assert not errors
        assert set(found) == {"skills/SKILL.md", "skills/nested/SKILL.md"}


async def test_304_metadata_still_checks_branch():
    calls = []

    def handler(r):
        calls.append(str(r.url))
        if "/commits/" in r.url.path:
            return httpx.Response(200, json={"sha": COMMIT, "commit": {"tree": {"sha": TREE}}})
        return httpx.Response(304)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        g = GitHub(client)
        meta, _ = await g.metadata(
            "test/repo", {"etag": "known", "data": {"private": False, "default_branch": "trunk"}}
        )
        assert await g.snapshot("test/repo", meta["default_branch"]) == (COMMIT, TREE)
        assert calls[-1].endswith("/commits/trunk")


async def test_response_size_bound():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 100))
    ) as client:
        with pytest.raises(FetchError, match="大小限制"):
            await GitHub(client).request("https://api.github.com/repos/test/repo", limit=20)

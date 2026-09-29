import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

CATEGORIES = ["Search", "Read", "Reason", "Experiment", "Write"]
STATES = {"required", "optional", "not_required", "unknown"}
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT.parent / "config" if (ROOT.parent / "config").exists() else ROOT / "defaults"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SKILL_HUB_DATA_DIR", "./data")))
    token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""), repr=False)
    host: str = field(default_factory=lambda: os.getenv("SKILL_HUB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("SKILL_HUB_PORT", "8765")))
    auto_start: bool = True

    def __post_init__(self):
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("仅允许监听本机回环地址")


def normalize_repo(value: str) -> str:
    value = value.strip()
    if "://" in value:
        u = urlsplit(value)
        if u.scheme != "https" or u.netloc != "github.com" or u.query or u.fragment:
            raise ValueError("仅接受 https://github.com/owner/repo 或 owner/repo")
        value = u.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", value):
        raise ValueError("仓库格式应为 owner/repo，不含额外路径或凭据")
    if value.split("/")[1] in {".", ".."}:
        raise ValueError("无效仓库名称")
    return value.lower()


def validate_path(value: str, file: bool = False) -> str:
    value = value.strip().rstrip("/")
    if not value or len(value) > 500 or any(c in value for c in "\\?#*\x00\n\r"):
        raise ValueError("扫描路径必须是非空的仓库相对路径")
    if any(p in {"", ".", ".."} for p in value.split("/")):
        raise ValueError("扫描路径不能包含空段、. 或 ..")
    if file and value.split("/")[-1] != "SKILL.md":
        raise ValueError("精确文件路径必须指向 SKILL.md")
    return value


def safe_link(value: str) -> bool:
    try:
        u = urlsplit(value)
        return (
            u.scheme in {"http", "https"} and bool(u.hostname) and not u.username and not u.password
        )
    except ValueError:
        return False

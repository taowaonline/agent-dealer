"""安全执行边界（P2-04）：基线快照、变更审计、密钥脱敏、信任 profile。

原则（与 SKILL.md §15 一致）：
- 可信本地（trusted-local）是默认威胁模型；
- 不可信（sandboxed-untrusted）必须启用沙箱与事件签名，否则拒绝启动；
- 文件系统基线 + 变更对比用于发现“实际修改超出 allowed_paths”，
  不只检查事件中申报的 artifacts。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Set

from .errors import E203_PATH_FORBIDDEN, E502_UNSAFE_PROFILE, MMACError

PROFILE_TRUSTED_LOCAL = "trusted-local"
PROFILE_SANDBOXED_UNTRUSTED = "sandboxed-untrusted"

SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----", "私钥"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI 风格 API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub token"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]", "疑似硬编码凭据"),
]

BASELINE_FILENAME = ".baseline.json"

# 基线与审计默认忽略的运行时路径段（按路径段精确匹配，避免子串误判/漏判）
DEFAULT_IGNORES = (
    ".git", "__pycache__", ".DS_Store", "locks", "tmp",
    ".baseline.json", ".runner-state.json",
)

# 密钥扫描的忽略集合：只忽略版本控制元数据与 Python 缓存。
# 注意：不忽略 `tmp/`——暂存产物同样可能泄露密钥，必须参与扫描。
SECRET_IGNORES = (".git", "__pycache__", ".DS_Store")


def _is_ignored(rel: str, ignores) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(ig in parts or rel == ig for ig in ignores)


def _iter_files(root: str) -> List[str]:
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for name in filenames:
            out.append(os.path.join(dirpath, name))
    return sorted(out)


def snapshot_baseline(root: str, ignores: Optional[List[str]] = None) -> Dict[str, str]:
    """对目录做文件哈希快照（不依赖 git）。返回 {相对路径: sha256}。"""
    ignores = ignores or list(DEFAULT_IGNORES)
    root = os.path.abspath(root)
    manifest: Dict[str, str] = {}
    for full in _iter_files(root):
        rel = os.path.relpath(full, root)
        if _is_ignored(rel, ignores):
            continue
        h = hashlib.sha256()
        try:
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        except OSError:
            continue
        manifest[rel] = h.hexdigest()
    return manifest


def save_baseline(root: str, manifest: Dict[str, str]) -> str:
    path = os.path.join(root, BASELINE_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    return path


def load_baseline(root: str) -> Optional[Dict[str, str]]:
    path = os.path.join(root, BASELINE_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def diff_baseline(old: Dict[str, str], new: Dict[str, str]) -> Dict[str, List[str]]:
    """对比两个快照。返回 {added, modified, deleted}。"""
    old_keys: Set[str] = set(old)
    new_keys: Set[str] = set(new)
    return {
        "added": sorted(new_keys - old_keys),
        "deleted": sorted(old_keys - new_keys),
        "modified": sorted(k for k in old_keys & new_keys if old[k] != new[k]),
    }


def check_changes_allowed(changed: List[str], allowed: List[str],
                          forbidden: List[str], root: str) -> List[str]:
    """返回越权变更列表（空 = 全部合规）。"""
    root = os.path.abspath(root)

    def resolve(spec: str) -> str:
        return os.path.realpath(spec if os.path.isabs(spec) else os.path.join(root, spec))

    allowed_roots = [resolve(s) for s in allowed] or [root]
    forbidden_roots = [resolve(s) for s in forbidden]

    def within(path: str, base: str) -> bool:
        try:
            return os.path.commonpath([path, base]) == base
        except ValueError:
            return False

    violations: List[str] = []
    for rel in changed:
        real = os.path.realpath(os.path.join(root, rel))
        if any(within(real, f) for f in forbidden_roots):
            violations.append(rel)
        elif not any(within(real, a) for a in allowed_roots):
            violations.append(rel)
    return violations


def scan_secrets(path: str) -> List[Dict[str, Any]]:
    """扫描文件中的疑似密钥。返回 [{file, line, kind}]。"""
    findings: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                for pattern, kind in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append({"file": path, "line": lineno, "kind": kind})
    except OSError:
        pass
    return findings


def scan_tree_secrets(root: str, ignores: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    # 密钥扫描不能继承 DEFAULT_IGNORES——tmp/ 等暂存目录同样可能泄露密钥。
    ignores = list(ignores) if ignores is not None else list(SECRET_IGNORES)
    findings: List[Dict[str, Any]] = []
    for full in _iter_files(root):
        rel = os.path.relpath(full, root)
        if _is_ignored(rel, ignores):
            continue
        if os.path.getsize(full) > 2 * 1024 * 1024:
            continue
        findings.extend(scan_secrets(full))
    return findings


def enforce_profile(profile: str, sandbox_enabled: bool, signing_enabled: bool) -> None:
    """不可信模式必须同时具备沙箱与签名，否则拒绝启动。"""
    if profile == PROFILE_SANDBOXED_UNTRUSTED and not (sandbox_enabled and signing_enabled):
        raise MMACError(E502_UNSAFE_PROFILE,
                        "sandboxed-untrusted 需要 sandbox_enabled 与 signing_enabled 同时为真")
    if profile not in (PROFILE_TRUSTED_LOCAL, PROFILE_SANDBOXED_UNTRUSTED):
        raise MMACError(E502_UNSAFE_PROFILE, "未知 profile: %r" % profile)


def redact(text: str) -> str:
    """对文本中的疑似密钥做脱敏。"""
    out = text
    for pattern, kind in SECRET_PATTERNS:
        out = re.sub(pattern, "<REDACTED:%s>" % kind, out)
    return out

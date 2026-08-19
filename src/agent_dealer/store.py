"""任务存储：目录锁、租约与唯一原子发布入口（P1-03 / P2-03）。

所有对 coordination.md 的写入必须经由 TaskStore.publish()，Agent 不再直接拼接日志。

publish 流程（与 SKILL.md §7 一致）：
1. 原子获取目录锁（os.mkdir，全平台原子）；
2. 锁内重新读取最新事件；
3. 用校验器对候选事件做只读预校验（含链、状态机、权限、产物）；
4. 固化版本化产物（tmp → 计算 SHA-256 → os.replace 原子重命名）；
5. 记录文件偏移，一次性追加完整事件块并 fsync；
6. 发布后复读校验；失败时截断回滚（锁未释放，无并发写者）；
7. 释放锁。

崩溃恢复：
- 锁目录含 owner.json（owner/created_at/lease_until）；租约过期可安全接管；
- tmp/ 中未被任何事件引用的孤儿产物由 cleanup_orphans() 清理；
- 追加点之后崩溃会在下次校验时暴露（链断裂/标记不配对），由人工按协议处理，
  publish 自身只在锁内回滚自己追加的字节。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import validator
from .errors import (
    E101_INVALID_STATE, E102_INVALID_EVENT, E301_HASH_MISMATCH,
    E401_LOCK_CONFLICT, E402_STALE_LOCK, MMACError,
)

LOCK_DIRNAME = "coordination.lock"
TASKS_DIRNAME = "tasks"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_event_id() -> str:
    return str(uuid.uuid4())


def _parse_aware_datetime(value: Any) -> Optional[datetime]:
    """解析 ISO 时间戳；无效或无时区（naive）返回 None，避免比较/运算时抛 TypeError。"""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class LockHandle:
    def __init__(self, store: "TaskStore", owner: str) -> None:
        self.store = store
        self.owner = owner
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.store.release_lock(self)
            self.released = True

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


class TaskStore:
    def __init__(self, task_dir: str) -> None:
        self.task_dir = os.path.abspath(task_dir)
        self.coord_path = os.path.join(self.task_dir, "coordination.md")
        self.lock_path = os.path.join(self.task_dir, "locks", LOCK_DIRNAME)
        self.tmp_dir = os.path.join(self.task_dir, "tmp")

    # ------------------------------------------------------------ 读取

    def read_text(self) -> str:
        with open(self.coord_path, encoding="utf-8") as fh:
            return fh.read()

    def read_events(self) -> List[Dict[str, Any]]:
        report = validator.ValidationReport(self.task_dir)
        return validator.parse_events(self.read_text(), report)

    def last_event(self) -> Optional[Dict[str, Any]]:
        events = self.read_events()
        return events[-1] if events else None

    def status(self) -> Optional[str]:
        last = self.last_event()
        return last.get("status") if last else None

    def validate(self, candidate: Optional[Dict[str, Any]] = None
                 ) -> validator.ValidationReport:
        return validator.validate_task(self.task_dir, candidate=candidate)

    # ------------------------------------------------------------ 锁

    def acquire_lock(self, owner: str, lease_seconds: int = 900,
                     wait_seconds: float = 0.0) -> LockHandle:
        import time
        deadline = time.time() + wait_seconds
        while True:
            try:
                os.mkdir(self.lock_path)
                break
            except FileExistsError:
                info = self.lock_info()
                if info is None:
                    # owner.json 缺失：可能是持锁者初始化中，也可能是初始化前崩溃。
                    # 目录 mtime 超过租约上限时视为崩溃残留，可安全接管。
                    if self._ownerless_lock_stale(lease_seconds):
                        self._reclaim_stale_lock(reason="锁无 owner.json 且超过租约上限，判定崩溃残留")
                        continue
                    if time.time() >= deadline:
                        raise MMACError(E401_LOCK_CONFLICT,
                                        "锁存在且无法读取 owner 信息，请人工检查")
                    time.sleep(0.05)
                    continue
                if self._lock_expired(info):
                    self._reclaim_stale_lock(reason="租约过期，安全接管")
                    continue
                if time.time() >= deadline:
                    raise MMACError(E401_LOCK_CONFLICT,
                                    "锁被 %s 持有，lease_until=%s"
                                    % (info.get("owner"), info.get("lease_until")))
                time.sleep(0.05)
            except FileNotFoundError:
                os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        now = datetime.now(timezone.utc).astimezone()
        info = {
            "owner": owner,
            "created_at": now.isoformat(timespec="seconds"),
            "lease_until": (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds"),
        }
        try:
            self._write_lock_info(info)
        except OSError:
            # owner.json 写失败：清理锁目录，避免留下永不解锁的残骸
            try:
                os.rmdir(self.lock_path)
            except OSError:
                pass
            raise
        return LockHandle(self, owner)

    def _write_lock_info(self, info: Dict[str, Any]) -> None:
        path = os.path.join(self.lock_path, "owner.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())

    def _ownerless_lock_stale(self, lease_seconds: int) -> bool:
        try:
            mtime = os.path.getmtime(self.lock_path)
        except OSError:
            return False
        age = datetime.now(timezone.utc).timestamp() - mtime
        return age > max(lease_seconds, 900) + 60

    def lock_info(self) -> Optional[Dict[str, Any]]:
        try:
            with open(os.path.join(self.lock_path, "owner.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def _lock_expired(self, info: Dict[str, Any]) -> bool:
        lease = info.get("lease_until")
        if not isinstance(lease, str):
            return True  # 损坏的 owner.json：判过期可回收，避免永久占用
        until = _parse_aware_datetime(lease)
        if until is None:
            return True  # 无法解析或缺少时区：视为损坏，判过期可回收
        return datetime.now(timezone.utc).astimezone() > until

    def _reclaim_stale_lock(self, reason: str) -> None:
        """原子接管过期锁：先 rename（原子，失败说明已被他人接管），确认后再删除。"""
        tomb = "%s.reclaim-%s" % (self.lock_path, uuid.uuid4().hex[:8])
        try:
            os.rename(self.lock_path, tomb)
        except OSError:
            return  # 已被他人接管或锁已消失
        marker = os.path.join(self.task_dir, "locks", "recovery.log")
        with open(marker, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (now_iso(), reason))
        shutil.rmtree(tomb, ignore_errors=True)

    def release_lock(self, handle: Optional[LockHandle], force: bool = False,
                     reason: str = "") -> None:
        # 先原子 rename 再校验/删除：避免"读 owner → 删目录"窗口内锁被他人
        # reclaim 重取后遭误删。rename 失败说明锁已不在，视为已释放。
        if not os.path.isdir(self.lock_path):
            return
        tomb = "%s.release-%s" % (self.lock_path, uuid.uuid4().hex[:8])
        try:
            os.rename(self.lock_path, tomb)
        except OSError:
            return
        if not force and handle is not None:
            info = None
            try:
                with open(os.path.join(tomb, "owner.json"), encoding="utf-8") as fh:
                    info = json.load(fh)
            except (OSError, json.JSONDecodeError):
                info = None
            if info and info.get("owner") != handle.owner:
                try:
                    os.rename(tomb, self.lock_path)
                except OSError:
                    # 放回失败：已有新持有者，留下 tomb 目录供人工核查
                    marker = os.path.join(self.task_dir, "locks", "recovery.log")
                    with open(marker, "a", encoding="utf-8") as fh:
                        fh.write("%s 释放校验失败，锁目录暂存于 %s\n" % (now_iso(), tomb))
                raise MMACError(E401_LOCK_CONFLICT, "不得释放他人持有的锁")
        if force and reason:
            marker = os.path.join(self.task_dir, "locks", "recovery.log")
            with open(marker, "a", encoding="utf-8") as fh:
                fh.write("%s %s\n" % (now_iso(), reason))
        shutil.rmtree(tomb, ignore_errors=True)

    # ------------------------------------------------------------ 租约（任务认领）

    def claim_lease_path(self, role: str) -> str:
        return os.path.join(self.task_dir, "locks", "claim-%s.json" % role)

    def write_lease(self, role: str, instance_id: str, lease_seconds: int = 900) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).astimezone()
        lease = {
            "role": role,
            "instance_id": instance_id,
            "created_at": now.isoformat(timespec="seconds"),
            "lease_until": (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds"),
            "last_heartbeat": now.isoformat(timespec="seconds"),
        }
        os.makedirs(os.path.dirname(self.claim_lease_path(role)), exist_ok=True)
        self._write_lease_atomic(role, lease)
        return lease

    def _write_lease_atomic(self, role: str, lease: Dict[str, Any]) -> None:
        path = self.claim_lease_path(role)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(lease, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def read_lease(self, role: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self.claim_lease_path(role), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def heartbeat(self, role: str) -> Optional[Dict[str, Any]]:
        lease = self.read_lease(role)
        if lease is None:
            return None
        now = datetime.now(timezone.utc).astimezone()
        lease["last_heartbeat"] = now.isoformat(timespec="seconds")
        # 心跳同时续租：活跃执行者不会因租约到期被误判失联。
        # 租约时长沿用原 lease_until - created_at，解析失败（含 naive 时间戳）回退默认 900s。
        lease_seconds = 900
        created = _parse_aware_datetime(lease.get("created_at"))
        until = _parse_aware_datetime(lease.get("lease_until"))
        if created is not None and until is not None:
            span = (until - created).total_seconds()
            if span > 0:
                lease_seconds = span
        lease["lease_until"] = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        self._write_lease_atomic(role, lease)
        return lease

    def lease_expired(self, role: str) -> bool:
        lease = self.read_lease(role)
        if not lease:
            return True
        until = _parse_aware_datetime(lease.get("lease_until"))
        hb = _parse_aware_datetime(lease.get("last_heartbeat"))
        if until is None or hb is None:
            return True  # 损坏的租约文件：判失联，允许接管
        now = datetime.now(timezone.utc).astimezone()
        return now > until or (now - hb) > timedelta(seconds=1200)

    # ------------------------------------------------------------ 产物

    def stage_artifact(self, src_path: str, dest_rel: str) -> Dict[str, Any]:
        """把产物原子固化到任务目录：读源文件 → 写 tmp → 校验哈希 → os.replace。

        dest_rel 必须是任务目录内的相对路径；拒绝绝对路径与 `..` 穿越。
        """
        if os.path.isabs(dest_rel):
            raise MMACError(E102_INVALID_EVENT, "产物目标必须为任务目录内相对路径: %r" % dest_rel)
        # task_dir 与 dest 必须使用相同的路径规范化策略（realpath 同时解析符号链接），
        # 否则在 macOS 等系统上 /tmp → /private/tmp 的符号链接会让 commonpath 误判越界。
        task_real = os.path.realpath(self.task_dir)
        dest = os.path.realpath(os.path.join(task_real, dest_rel))
        if os.path.commonpath([dest, task_real]) != task_real:
            raise MMACError(E102_INVALID_EVENT, "产物目标越出任务目录: %r" % dest_rel)
        digest = sha256_file(src_path)
        os.makedirs(self.tmp_dir, exist_ok=True)
        tmp_path = os.path.join(self.tmp_dir, os.path.basename(dest_rel) + ".stage")
        with open(src_path, "rb") as src, open(tmp_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(tmp_path, dest)
        if sha256_file(dest) != digest:
            raise MMACError(E301_HASH_MISMATCH, "产物固化后哈希不一致: %s" % dest_rel)
        return {"path": dest_rel, "sha256": digest}

    def cleanup_orphans(self) -> List[str]:
        """清理 tmp/ 下未被引用的暂存文件（崩溃残留）。返回清理列表。"""
        removed: List[str] = []
        if not os.path.isdir(self.tmp_dir):
            return removed
        # 活跃持锁者可能在写 .stage 暂存；此时跳过清理，避免破坏进行中的 publish。
        if os.path.isdir(self.lock_path):
            info = self.lock_info()
            if info is not None and not self._lock_expired(info):
                return removed
        for name in os.listdir(self.tmp_dir):
            if name.endswith(".stage"):
                os.unlink(os.path.join(self.tmp_dir, name))
                removed.append(name)
        return removed

    # ------------------------------------------------------------ 发布

    def publish(self, event: Dict[str, Any], owner: str,
                artifact_sources: Optional[Dict[str, str]] = None,
                lease_seconds: int = 900,
                wait_seconds: float = 30.0,
                auto_previous: bool = True) -> Dict[str, Any]:
        """唯一事件发布入口。artifact_sources: {事件内相对路径: 源文件绝对路径}。

        auto_previous=True 时在锁内把 previous_event_id 设为最新事件，
        调用方无需（也不应）猜测链尾。
        """
        if not isinstance(event, dict):
            raise MMACError(E102_INVALID_EVENT, "事件必须为 JSON 对象")
        event = dict(event)

        with self.acquire_lock(owner, lease_seconds=lease_seconds,
                               wait_seconds=wait_seconds):
            # 1. 锁内重读链尾
            last = self.last_event()
            if auto_previous:
                event["previous_event_id"] = last["event_id"] if last else None
            elif (last and event.get("previous_event_id") != last.get("event_id")) \
                    or (not last and event.get("previous_event_id") is not None):
                raise MMACError(E101_INVALID_STATE, "previous_event_id 与链尾不一致")

            # 2. 字段级预检（在任何文件固化之前）。待固化的产物由 stage_artifact
            # 自身强制路径安全（拒绝绝对路径/穿越），此处先校验其余字段与已申报产物。
            pre_event = dict(event)
            if artifact_sources:
                pre_event["artifacts"] = [
                    a for a in event.get("artifacts", [])
                    if not (isinstance(a, dict) and a.get("path") in artifact_sources)
                ]
            pre = validator.ValidationReport(self.task_dir)
            validator.validate_event_fields(0, pre_event, pre)
            if pre.errors:
                raise MMACError(E102_INVALID_EVENT,
                                "候选事件字段非法: " + "; ".join(i.message for i in pre.errors[:3]))

            # 3. 固化产物并回填哈希；失败时清理本次已固化的文件
            staged_paths: List[str] = []
            try:
                if artifact_sources:
                    arts = []
                    for a in event.get("artifacts", []):
                        a = dict(a)
                        src = artifact_sources.get(a.get("path"))
                        if src:
                            staged = self.stage_artifact(src, a["path"])
                            a["sha256"] = staged["sha256"]
                            staged_paths.append(a["path"])
                        arts.append(a)
                    event["artifacts"] = arts

                # 4. 候选全量预校验（只读，含产物哈希）
                report = self.validate(candidate=event)
                if not report.ok:
                    raise MMACError(E102_INVALID_EVENT,
                                    "候选事件预校验失败: " + "; ".join(i.message for i in report.errors[:3]))

                # 5. 长操作后续租，避免持锁超时被接管
                self._renew_lock_lease(owner, lease_seconds)

                # 6. 一次性追加 + fsync；任何异常都截断回滚（仍持有锁，无并发写者）
                block = "\n" + validator.serialize_event(event) + "\n"
                with open(self.coord_path, "a", encoding="utf-8") as fh:
                    offset = fh.tell()
                    try:
                        fh.write(block)
                        fh.flush()
                        os.fsync(fh.fileno())
                    except OSError:
                        fh.truncate(offset)
                        raise

                # 7. 发布后复核；失败则截断回滚
                post = self.validate()
                if not post.ok:
                    with open(self.coord_path, "r+", encoding="utf-8") as fh:
                        fh.truncate(offset)
                    raise MMACError(E102_INVALID_EVENT,
                                    "发布后复核失败，已回滚: " + "; ".join(i.message for i in post.errors[:3]))
            except Exception:
                for rel in staged_paths:
                    try:
                        os.unlink(os.path.join(self.task_dir, rel))
                    except OSError:
                        pass
                raise

        return event

    def _renew_lock_lease(self, owner: str, lease_seconds: int) -> None:
        info = self.lock_info()
        if not info or info.get("owner") != owner:
            return
        now = datetime.now(timezone.utc).astimezone()
        info["lease_until"] = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        try:
            self._write_lock_info(info)
        except OSError:
            pass

"""协议数据模型（P1-01）：严格字段、schema 版本、round-trip 序列化。

所有 from_dict 拒绝未知关键字段；to_dict/from_dict 可 round-trip。
仅使用 Python 3.9+ 标准库。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .errors import E102_INVALID_EVENT, E103_SCHEMA_VERSION, E105_INVALID_CONTROL, MMACError

SCHEMA_VERSION = "1.0"
SUPPORTED_PROTOCOL_VERSIONS = {"1.0"}

EVENT_TYPES = [
    "TASK_CREATED", "PLANNING_STARTED", "PLAN_READY", "TASK_DECOMPOSED",
    "TASK_CLAIMED", "TASK_RECLAIMED", "EXECUTION_STARTED", "HEARTBEAT",
    "WORK_READY", "REVIEW_STARTED", "REVIEW_APPROVED", "REVISION_REQUIRED",
    "REVISION_STARTED", "TASK_BLOCKED", "TASK_FAILED", "TASK_CANCELLED",
    "TASK_REOPENED", "ROLE_OVERRIDE", "EVENT_REJECTED",
]

STATUSES = [
    "CREATED", "PLANNING", "PLAN_READY", "CLAIMED", "EXECUTING",
    "WORK_READY", "REVIEWING", "APPROVED", "REVISION_REQUIRED",
    "BLOCKED", "FAILED", "CANCELLED",
]

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _check_unknown(data: Dict[str, Any], allowed: set, where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MMACError(E102_INVALID_EVENT, "%s 含未知字段: %s" % (where, ", ".join(unknown)))


def _req_str(data: Dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MMACError(E102_INVALID_EVENT, "%s.%s 必须为非空字符串" % (where, key))
    return value


def _opt_str(data: Dict[str, Any], key: str, where: str) -> Optional[str]:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MMACError(E102_INVALID_EVENT, "%s.%s 必须为字符串或 null" % (where, key))
    return value


class ArtifactRef:
    FIELDS = {"path", "sha256", "media_type", "version"}

    def __init__(self, path: str, sha256: str, media_type: str, version: int) -> None:
        if not path or not isinstance(path, str):
            raise MMACError(E102_INVALID_EVENT, "artifact.path 必须为非空字符串")
        if not SHA256_RE.match(sha256 or ""):
            raise MMACError(E102_INVALID_EVENT, "artifact.sha256 非法: %r" % sha256)
        if not media_type or not isinstance(media_type, str):
            raise MMACError(E102_INVALID_EVENT, "artifact.media_type 必须为非空字符串")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise MMACError(E102_INVALID_EVENT, "artifact.version 必须为 >=1 整数")
        self.path = path
        self.sha256 = sha256
        self.media_type = media_type
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRef":
        if not isinstance(data, dict):
            raise MMACError(E102_INVALID_EVENT, "artifact 必须为对象")
        _check_unknown(data, cls.FIELDS, "artifact")
        return cls(
            path=_req_str(data, "path", "artifact"),
            sha256=_req_str(data, "sha256", "artifact"),
            media_type=_req_str(data, "media_type", "artifact"),
            version=data.get("version"),
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ArtifactRef) and self.to_dict() == other.to_dict()


class AgentIdentity:
    FIELDS = {"role", "instance_id", "provider", "client", "model"}

    def __init__(self, role: str, instance_id: str, provider: str, client: str, model: str) -> None:
        self.role = role
        self.instance_id = instance_id
        self.provider = provider
        self.client = client
        self.model = model

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "instance_id": self.instance_id,
            "provider": self.provider,
            "client": self.client,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], where: str = "actor") -> "AgentIdentity":
        if not isinstance(data, dict):
            raise MMACError(E102_INVALID_EVENT, "%s 必须为对象" % where)
        _check_unknown(data, cls.FIELDS, where)
        return cls(
            role=_req_str(data, "role", where),
            instance_id=_req_str(data, "instance_id", where),
            provider=_req_str(data, "provider", where),
            client=_req_str(data, "client", where),
            model=_req_str(data, "model", where),
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, AgentIdentity) and self.to_dict() == other.to_dict()


class Event:
    FIELDS = {
        "protocol_version", "event_id", "previous_event_id", "task_id",
        "parent_task_id", "type", "status", "actor", "recipient", "caused_by",
        "revision_cycle", "timestamp", "artifacts", "summary", "payload",
    }

    def __init__(
        self,
        event_id: str,
        previous_event_id: Optional[str],
        task_id: str,
        type: str,
        status: str,
        actor: AgentIdentity,
        recipient_role: Optional[str],
        caused_by: Optional[str],
        revision_cycle: int,
        timestamp: str,
        artifacts: Optional[List[ArtifactRef]] = None,
        summary: str = "",
        payload: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        protocol_version: str = SCHEMA_VERSION,
    ) -> None:
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise MMACError(E103_SCHEMA_VERSION, "protocol_version=%r 不受支持" % protocol_version)
        if type not in EVENT_TYPES:
            raise MMACError(E102_INVALID_EVENT, "未知事件类型: %r" % type)
        if status not in STATUSES:
            raise MMACError(E102_INVALID_EVENT, "未知状态: %r" % status)
        if not ISO_RE.match(timestamp or ""):
            raise MMACError(E102_INVALID_EVENT, "timestamp 非法: %r" % timestamp)
        if not isinstance(revision_cycle, int) or isinstance(revision_cycle, bool) or revision_cycle < 0:
            raise MMACError(E102_INVALID_EVENT, "revision_cycle 必须为非负整数")
        self.protocol_version = protocol_version
        self.event_id = event_id
        self.previous_event_id = previous_event_id
        self.task_id = task_id
        self.parent_task_id = parent_task_id
        self.type = type
        self.status = status
        self.actor = actor
        self.recipient_role = recipient_role
        self.caused_by = caused_by
        self.revision_cycle = revision_cycle
        self.timestamp = timestamp
        self.artifacts = artifacts or []
        self.summary = summary
        self.payload = payload or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "event_id": self.event_id,
            "previous_event_id": self.previous_event_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "type": self.type,
            "status": self.status,
            "actor": self.actor.to_dict(),
            "recipient": {"role": self.recipient_role},
            "caused_by": self.caused_by,
            "revision_cycle": self.revision_cycle,
            "timestamp": self.timestamp,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "summary": self.summary,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        if not isinstance(data, dict):
            raise MMACError(E102_INVALID_EVENT, "事件顶层必须为对象")
        _check_unknown(data, cls.FIELDS, "event")
        recipient = data.get("recipient")
        if not isinstance(recipient, dict):
            raise MMACError(E102_INVALID_EVENT, "recipient 必须为对象")
        _check_unknown(recipient, {"role"}, "recipient")
        artifacts_raw = data.get("artifacts")
        if not isinstance(artifacts_raw, list):
            raise MMACError(E102_INVALID_EVENT, "artifacts 必须为数组")
        return cls(
            protocol_version=_req_str(data, "protocol_version", "event"),
            event_id=_req_str(data, "event_id", "event"),
            previous_event_id=_opt_str(data, "previous_event_id", "event"),
            task_id=_req_str(data, "task_id", "event"),
            parent_task_id=_opt_str(data, "parent_task_id", "event"),
            type=_req_str(data, "type", "event"),
            status=_req_str(data, "status", "event"),
            actor=AgentIdentity.from_dict(data.get("actor"), "actor"),
            recipient_role=_opt_str(recipient, "role", "recipient"),
            caused_by=_opt_str(data, "caused_by", "event"),
            revision_cycle=data.get("revision_cycle"),
            timestamp=_req_str(data, "timestamp", "event"),
            artifacts=[ArtifactRef.from_dict(a) for a in artifacts_raw],
            summary=data.get("summary") if isinstance(data.get("summary"), str) else "",
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Event) and self.to_dict() == other.to_dict()


class QualityGate:
    FIELDS = {
        "enabled", "strict", "target_score", "max_score", "max_revision_cycles",
        "blocking_issues_must_be_zero", "require_tests_when_applicable", "require_evidence",
    }

    def __init__(
        self,
        enabled: bool = True,
        strict: bool = True,
        target_score: int = 90,
        max_score: int = 100,
        max_revision_cycles: int = 3,
        blocking_issues_must_be_zero: bool = True,
        require_tests_when_applicable: bool = True,
        require_evidence: bool = True,
    ) -> None:
        for name, value in (("target_score", target_score), ("max_score", max_score),
                            ("max_revision_cycles", max_revision_cycles)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise MMACError(E105_INVALID_CONTROL, "quality_gate.%s 必须为非负整数" % name)
        if target_score > max_score:
            raise MMACError(E105_INVALID_CONTROL, "target_score 不得高于 max_score")
        self.enabled = bool(enabled)
        self.strict = bool(strict)
        self.target_score = target_score
        self.max_score = max_score
        self.max_revision_cycles = max_revision_cycles
        self.blocking_issues_must_be_zero = bool(blocking_issues_must_be_zero)
        self.require_tests_when_applicable = bool(require_tests_when_applicable)
        self.require_evidence = bool(require_evidence)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in sorted(self.FIELDS)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityGate":
        _check_unknown(data, cls.FIELDS, "quality_gate")
        return cls(**{k: data[k] for k in cls.FIELDS if k in data})

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, QualityGate) and self.to_dict() == other.to_dict()


class Subtask:
    FIELDS = {"subtask_id", "owner", "description", "file_ownership"}

    def __init__(self, subtask_id: str, owner: str,
                 description: str = "",
                 file_ownership: Optional[List[str]] = None) -> None:
        self.subtask_id = subtask_id
        self.owner = owner
        self.description = description
        self.file_ownership = file_ownership or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "owner": self.owner,
            "description": self.description,
            "file_ownership": list(self.file_ownership),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subtask":
        _check_unknown(data, cls.FIELDS, "subtask")
        return cls(
            subtask_id=_req_str(data, "subtask_id", "subtask"),
            owner=_req_str(data, "owner", "subtask"),
            description=data.get("description") or "",
            file_ownership=list(data.get("file_ownership") or []),
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Subtask) and self.to_dict() == other.to_dict()


class ControlConfig:
    """control.md 的结构化表示（安全 YAML 子集解析）。"""

    FIELDS = {"protocol", "task", "workflow", "agents", "quality_gate",
              "rubric", "permissions", "budget", "notes", "mapping_history"}

    REQUIRED_WORKFLOW = ("planning_agent", "default_executor", "multimodal_executor", "reviewer")

    def __init__(self, raw: Dict[str, Any]) -> None:
        _check_unknown(raw, self.FIELDS, "control")
        self.raw = raw
        workflow = raw.get("workflow") or {}
        for field in self.REQUIRED_WORKFLOW:
            if field not in workflow:
                raise MMACError(E105_INVALID_CONTROL, "control 缺少 workflow.%s" % field)
        self.workflow = workflow
        self.task = raw.get("task") or {}
        self.agents = raw.get("agents") or {}
        self.quality_gate = QualityGate.from_dict(raw.get("quality_gate") or {})
        self.rubric = raw.get("rubric") or {}
        self.permissions = raw.get("permissions") or {}
        self.budget = raw.get("budget") or {}
        if self.rubric:
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in self.rubric.values()):
                raise MMACError(E105_INVALID_CONTROL, "rubric 权重必须全部为整数")
            if sum(self.rubric.values()) != 100:
                raise MMACError(E105_INVALID_CONTROL, "rubric 权重总和必须为 100")
        for field in ("allowed_paths", "forbidden_paths"):
            value = self.permissions.get(field)
            if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
                raise MMACError(E105_INVALID_CONTROL, "permissions.%s 必须为字符串数组" % field)

    @property
    def task_id(self) -> str:
        return str(self.task.get("id", ""))

    @property
    def agent_roles(self) -> List[str]:
        return sorted(self.agents.keys())

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.raw)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlConfig":
        return cls(data)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ControlConfig) and self.raw == other.raw

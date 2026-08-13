"""MMAC 稳定错误码（P1-04）。

每个错误码包含：稳定编码、人类可读原因、下一步修复建议。
CLI 文本输出包含修复建议；``--json`` 输出稳定结构。

编码分段：
- E1xx 协议/状态机/事件结构
- E2xx 角色与权限
- E3xx 产物与哈希
- E4xx 锁与租约
- E5xx 审批与副作用
- E6xx Runner 与客户端
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class ErrorSpec:
    def __init__(self, code: str, reason: str, hint: str) -> None:
        self.code = code
        self.reason = reason
        self.hint = hint

    def format(self, detail: str = "") -> str:
        msg = "[%s] %s" % (self.code, self.reason)
        if detail:
            msg += "：" + detail
        return msg + " | 建议: " + self.hint


SPECS = {}


def _reg(code: str, reason: str, hint: str) -> ErrorSpec:
    spec = ErrorSpec(code, reason, hint)
    SPECS[code] = spec
    return spec


E101_INVALID_STATE = _reg(
    "MMAC-E101_INVALID_STATE", "非法状态流转",
    "对照 SKILL.md/references/state-machine.md 的状态机，检查事件 type/status；"
    "用 `agent-dealer status <task>` 查看当前状态")
E102_INVALID_EVENT = _reg(
    "MMAC-E102_INVALID_EVENT", "事件结构非法",
    "运行 `agent-dealer doctor <task>` 定位字段问题；参照 references/event-schema.md")
E103_SCHEMA_VERSION = _reg(
    "MMAC-E103_SCHEMA_VERSION", "schema 版本不兼容",
    "确认 protocol_version/schema 版本受支持；必要时先运行迁移工具")
E104_BROKEN_CHAIN = _reg(
    "MMAC-E104_BROKEN_CHAIN", "事件链断裂或分叉",
    "previous_event_id 必须等于当前最新事件；分叉时停止自动推进并由协调器裁定")
E105_INVALID_CONTROL = _reg(
    "MMAC-E105_INVALID_CONTROL", "control.md 配置非法",
    "运行 `agent-dealer doctor <task>`；对照 references/control-schema.md 修复")

E201_UNAUTHORIZED_ROLE = _reg(
    "MMAC-E201_UNAUTHORIZED_ROLE", "角色无权发布该事件",
    "检查 control.md 的 workflow/agents 映射；如需接管由协调器发布 ROLE_OVERRIDE")
E202_PLACEHOLDER_MODEL = _reg(
    "MMAC-E202_PLACEHOLDER_MODEL", "actor.model 为占位符",
    "填写真实模型标识，如 gpt-5.6-luna / glm-5.2 / kimi-k2.5")
E203_PATH_FORBIDDEN = _reg(
    "MMAC-E203_PATH_FORBIDDEN", "路径越权",
    "产物必须位于 permissions.allowed_paths 内且不得命中 forbidden_paths；禁止 `..` 穿越")

E301_HASH_MISMATCH = _reg(
    "MMAC-E301_HASH_MISMATCH", "产物 SHA-256 不一致",
    "重新计算哈希：`shasum -a 256 <file>`；若产物被后续事件 supersede，确认版本号递增")
E302_ARTIFACT_MISSING = _reg(
    "MMAC-E302_ARTIFACT_MISSING", "产物文件缺失",
    "确认路径相对任务目录（任务目录外用绝对路径）；用 `agent-dealer artifact add` 固化产物")
E303_TAMPERED_LOG = _reg(
    "MMAC-E303_TAMPERED_LOG", "事件日志被篡改或损坏",
    "coordination.md 只追加；恢复备份或由协调器发布 EVENT_REJECTED")

E401_LOCK_CONFLICT = _reg(
    "MMAC-E401_LOCK_CONFLICT", "协调锁被占用",
    "读取 locks/coordination.lock/owner.json 确认租约；未过期则等待，过期可安全接管")
E402_STALE_LOCK = _reg(
    "MMAC-E402_STALE_LOCK", "检测到过期锁",
    "确认 owner 失联后删除锁目录并记录恢复原因")
E403_LEASE_EXPIRED = _reg(
    "MMAC-E403_LEASE_EXPIRED", "任务租约过期",
    "原执行者失联；满足恢复条件后发布 TASK_RECLAIMED 接管")

E501_APPROVAL_REQUIRED = _reg(
    "MMAC-E501_APPROVAL_REQUIRED", "操作需要人工审批",
    "该副作用命中 require_human_approval_for；获得用户明确授权后再执行")
E502_UNSAFE_PROFILE = _reg(
    "MMAC-E502_UNSAFE_PROFILE", "不可信模式缺少沙箱",
    "sandboxed-untrusted profile 必须启用沙箱与事件签名，否则拒绝启动")

E601_RUNNER = _reg(
    "MMAC-E601_RUNNER", "Runner/adapter 错误",
    "检查 adapters 配置与客户端可用性：`agent-dealer doctor <task>`")
E602_CLIENT_UNAVAILABLE = _reg(
    "MMAC-E602_CLIENT_UNAVAILABLE", "客户端不可用",
    "确认对应 CLI 已安装并在 PATH 中，或改用 manual adapter")


class MMACError(Exception):
    """带稳定错误码的协议异常。"""

    def __init__(self, spec: ErrorSpec, detail: str = "") -> None:
        self.spec = spec
        self.detail = detail
        super().__init__(spec.format(detail))

    @property
    def code(self) -> str:
        return self.spec.code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.spec.code,
            "reason": self.spec.reason,
            "detail": self.detail,
            "hint": self.spec.hint,
        }


def format_issue(code: Optional[str], message: str) -> str:
    """把自由文本校验信息前缀上稳定错误码（可选）。"""
    if code:
        return "[%s] %s" % (code, message)
    return message

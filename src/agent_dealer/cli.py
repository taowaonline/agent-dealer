"""agent_dealer CLI（P1-02 / P1-03 / P1-04）。

子命令：
  init      创建任务目录、control.md、目录结构并发布 TASK_CREATED
  doctor    环境 + 配置 + 事件链 + 产物 + 锁 + 密钥扫描综合诊断
  status    人类可读状态摘要（--json 机器可读）
  next      下一步应由谁行动（--role 过滤）
  claim     发布 TASK_CLAIMED 并写入租约
  event     prepare 生成候选事件 JSON 模板
  publish   唯一原子发布入口（锁 + 预校验 + 产物固化 + 追加 + 复核）
  artifact  add 固化产物并输出 ArtifactRef JSON
  validate  校验任务（等价 python -m agent_dealer.validator）
  watch     Runner 监听调度循环
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

from . import validator
from .errors import E202_PLACEHOLDER_MODEL, MMACError
from .models import SCHEMA_VERSION
from .security import scan_tree_secrets
from .store import TaskStore, new_event_id, now_iso

CONTROL_TEMPLATE = """```yaml
protocol:
  name: cross-model-file-collaboration
  version: "1.0"

task:
  id: {task_id}
  title: {title}
  created_at: {created_at}
  owner: human

workflow:
  mode: {mode}
  planning_agent: {planner}
  default_executor: {executor}
  multimodal_executor: {multimodal}
  reviewer: {reviewer}
  allow_parallel_execution: false
  poll_interval_seconds: 5
  claim_lease_seconds: 900
  stale_agent_timeout_seconds: 1200

agents:
{agents_block}

quality_gate:
  enabled: true
  strict: true
  target_score: 90
  max_score: 100
  max_revision_cycles: 3
  blocking_issues_must_be_zero: true
  require_tests_when_applicable: true
  require_evidence: true

rubric:
  requirement_fulfillment: 30
  correctness: 25
  tests_and_verification: 20
  maintainability: 10
  security_and_risk: 10
  documentation: 5

permissions:
  allowed_paths: ["./"]
  forbidden_paths: [".git/"]
  allow_network: false
  allow_external_messages: false
  allow_destructive_actions: false

budget:
  max_cost_weight: 30
  prefer_lowest_cost_capable_agent: true
```
"""

COORD_HEADER = "# Coordination Log — {task_id}\n\n本文件只追加完整事件块，是任务协作状态的唯一事实来源。\n"

CLIENT_CANDIDATES = ["codex", "claude", "kimi", "cursor", "gemini"]


def _out(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


SOLO_AGENT_TEMPLATE = """  {role}:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [architecture, planning, review, coding, testing, documentation, vision, image-analysis]
    cost_weight: 1
    note: solo 模式——本角色由单一会话扮演 A/B/C 全部职责；REVIEW_APPROVED 需 self_review + reproduced_commands（validator 强制），批准为临时性，可被后续独立审查覆盖"""

MULTI_AGENTS_TEMPLATE = """  {planner}:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [architecture, planning, review, reasoning]
    cost_weight: 5
  {executor}:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [coding, testing, documentation, file-processing]
    cost_weight: 1
  {multimodal}:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [vision, image-analysis, multimodal]
    cost_weight: 3"""


def cmd_init(args: argparse.Namespace) -> int:
    actor = _actor_from_args(args, "coordinator")  # 先校验 model，再落盘
    tasks_root = args.tasks_dir
    task_dir = os.path.join(tasks_root, args.task_id)
    if os.path.exists(task_dir):
        print("✗ 任务目录已存在: %s" % task_dir)
        return 1
    for sub in ("artifacts/plans", "artifacts/executions", "artifacts/reviews",
                "artifacts/media", "locks", "tmp"):
        os.makedirs(os.path.join(task_dir, sub), exist_ok=True)

    if args.solo:
        # 单会话模式：一个角色扮演 planner/executor/multimodal/reviewer。
        # 角色门槛放宽，但 REVIEW_APPROVED 必须自证（validator solo-review 规则）。
        solo_role = args.executor or "B"
        planner = executor = multimodal = reviewer = solo_role
        agents_block = SOLO_AGENT_TEMPLATE.format(role=solo_role)
        mode = "solo"
    else:
        planner, executor = args.planner, args.executor
        multimodal, reviewer = args.multimodal, args.reviewer
        agents_block = MULTI_AGENTS_TEMPLATE.format(
            planner=planner, executor=executor, multimodal=multimodal)
        mode = "multi"

    control = CONTROL_TEMPLATE.format(
        task_id=args.task_id, title=args.title, created_at=now_iso(),
        mode=mode, agents_block=agents_block,
        planner=planner, executor=executor,
        multimodal=multimodal, reviewer=reviewer,
    )
    with open(os.path.join(task_dir, "control.md"), "w", encoding="utf-8") as fh:
        fh.write(control)
    with open(os.path.join(task_dir, "coordination.md"), "w", encoding="utf-8") as fh:
        fh.write(COORD_HEADER.format(task_id=args.task_id))

    event = {
        "protocol_version": SCHEMA_VERSION,
        "event_id": new_event_id(),
        "previous_event_id": None,
        "task_id": args.task_id,
        "parent_task_id": None,
        "type": "TASK_CREATED",
        "status": "CREATED",
        "actor": actor,
        "recipient": {"role": solo_role if args.solo else args.planner},
        "caused_by": None,
        "revision_cycle": 0,
        "timestamp": now_iso(),
        "artifacts": [],
        "summary": "任务创建：%s" % args.title,
        "payload": {"goal": args.goal or args.title},
    }
    store = TaskStore(task_dir)
    store.publish(event, owner=args.instance_id)
    print("✓ 已创建 %s（TASK_CREATED 已发布并通过校验）" % task_dir)
    print("  下一步: agent_dealer next %s" % task_dir)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    problems: List[str] = []
    notes: List[str] = []

    # 1. 协议校验
    report = store.validate()
    for issue in report.errors:
        problems.append(issue.message)
    for issue in report.warnings:
        notes.append(issue.message)

    # 2. 锁状态
    info = store.lock_info()
    if os.path.isdir(store.lock_path):
        if info and store._lock_expired(info):
            problems.append("发现过期协调锁（owner=%s），可安全接管" % info.get("owner"))
        elif info:
            notes.append("协调锁被 %s 持有，lease_until=%s" % (info.get("owner"), info.get("lease_until")))
        else:
            problems.append("协调锁存在但 owner.json 不可读")

    # 3. 孤儿暂存
    orphans = store.cleanup_orphans()
    if orphans:
        notes.append("已清理 tmp 孤儿暂存: %s" % ", ".join(orphans))

    # 4. 客户端可用性
    clients = {c: bool(shutil.which(c)) for c in CLIENT_CANDIDATES}
    if not any(clients.values()):
        notes.append("PATH 中未发现任何已知客户端 CLI；可使用 manual adapter")

    # 5. 密钥扫描
    findings = scan_tree_secrets(args.task_dir)
    for f in findings:
        problems.append("疑似密钥泄露: %s:%d (%s)" % (f["file"], f["line"], f["kind"]))

    result = {
        "task_dir": args.task_dir,
        "ok": not problems,
        "status": report.final_status,
        "event_count": len(report.events),
        "problems": problems,
        "notes": notes,
        "clients": clients,
    }
    if args.json:
        _out(result, True)
    else:
        print("doctor: %s" % ("健康 ✓" if not problems else "发现 %d 个问题 ✗" % len(problems)))
        print("状态: %s | 事件数: %d" % (report.final_status, len(report.events)))
        for p in problems:
            print("✗ " + p)
        for n in notes:
            print("⚠ " + n)
        print("客户端: " + ", ".join("%s=%s" % (k, "✓" if v else "✗") for k, v in clients.items()))
    return 0 if not problems else 1


def cmd_status(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    report = store.validate()
    if args.json:
        _out(report.to_dict(), True)
        return 0 if report.ok else 1
    print(validator.format_report(report))
    if report.events:
        last = report.events[-1]
        print("最近事件摘要: %s" % last.get("summary", ""))
        approvals = [e for e in report.events if e.get("type") == "REVIEW_APPROVED"]
        if approvals:
            payload = approvals[-1].get("payload") or {}
            if payload.get("self_review") is True:
                print("批准性质: solo 自审临时批准——未经独立第二模型复核，后续独立审查可覆盖")
    return 0 if report.ok else 1


def cmd_next(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    report = store.validate()
    if not report.ok:
        print("✗ 任务链存在错误，先运行 doctor 修复")
        return 1
    status = report.final_status
    if status in validator.TERMINAL:
        _out({"done": True, "status": status, "message": "任务处于终态 %s" % status}, args.json)
        return 0
    workflow = (report.control or {}).get("workflow", {})
    routing = {
        "CREATED": (workflow.get("planning_agent"), "开始规划：发布 PLANNING_STARTED"),
        "PLANNING": (workflow.get("planning_agent"), "完成方案并发布 PLAN_READY"),
        "PLAN_READY": (workflow.get("default_executor"), "认领并执行：TASK_CLAIMED → EXECUTION_STARTED"),
        "CLAIMED": (None, "执行者继续：EXECUTION_STARTED"),
        "EXECUTING": (None, "执行者继续：交付 WORK_READY"),
        "WORK_READY": (workflow.get("reviewer"), "收齐交付后审查：REVIEW_STARTED"),
        "REVIEWING": (workflow.get("reviewer"), "完成审查：APPROVED / REVISION_REQUIRED / BLOCKED"),
        "REVISION_REQUIRED": (None, "被指派的执行者返工：REVISION_STARTED"),
    }
    role, action = routing.get(status, (None, "未知状态"))
    if report.events:
        recipient = (report.events[-1].get("recipient") or {}).get("role")
        if recipient:
            role = recipient
    result = {"done": False, "status": status, "next_role": role, "action": action}
    if args.role and role and args.role != role:
        result["message"] = "角色 %s 当前无待办；下一行动角色为 %s" % (args.role, role)
    _out(result, args.json)
    return 0


def _actor_from_args(args: argparse.Namespace, role: str) -> Dict[str, str]:
    model = args.model
    if not model or validator.is_placeholder_model(model):
        raise MMACError(
            E202_PLACEHOLDER_MODEL,
            "必须通过 --model 或环境变量 MMAC_MODEL 提供真实模型标识（当前: %r）" % model)
    return {
        "role": role,
        "instance_id": args.instance_id,
        "provider": args.provider,
        "client": args.client,
        "model": model,
    }


def cmd_claim(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    last = store.last_event()
    if last is None:
        print("✗ 空任务无法认领")
        return 1
    # 先计算租约；publish 成功后才落租约文件，避免事件失败留下孤儿租约
    from datetime import datetime, timedelta, timezone
    lease_until = (datetime.now(timezone.utc).astimezone()
                   + timedelta(seconds=900)).isoformat(timespec="seconds")
    payload: Dict[str, Any] = {"lease_until": lease_until}
    if args.subtask_id:
        payload["subtask_id"] = args.subtask_id
    event = {
        "protocol_version": SCHEMA_VERSION,
        "event_id": new_event_id(),
        "previous_event_id": None,  # publish 自动回填
        "task_id": last["task_id"],
        "parent_task_id": None,
        "type": "TASK_CLAIMED",
        "status": "CLAIMED",
        "actor": _actor_from_args(args, args.role),
        "recipient": {"role": args.role},
        "caused_by": last["event_id"],
        "revision_cycle": last.get("revision_cycle", 0),
        "timestamp": now_iso(),
        "artifacts": [],
        "summary": args.summary or "%s 认领任务" % args.role,
        "payload": payload,
    }
    store.publish(event, owner=args.instance_id)
    store.write_lease(args.role, args.instance_id)
    print("✓ TASK_CLAIMED 已发布（lease_until=%s）" % lease_until)
    return 0


def cmd_event_prepare(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    last = store.last_event()
    etype = args.type
    status = validator.EVENT_EXPECTED_STATUS.get(etype)
    if status is None and etype in validator.EVENT_EXPECTED_STATUS:
        status = store.status()
    event = {
        "protocol_version": SCHEMA_VERSION,
        "event_id": new_event_id(),
        "previous_event_id": last["event_id"] if last else None,
        "task_id": (last or {}).get("task_id", os.path.basename(args.task_dir)),
        "parent_task_id": None,
        "type": etype,
        "status": status or "<填写事件发布后的任务状态>",
        "actor": _actor_from_args(args, args.role),
        "recipient": {"role": args.recipient},
        "caused_by": last["event_id"] if last else None,
        "revision_cycle": (last or {}).get("revision_cycle", 0),
        "timestamp": now_iso(),
        "artifacts": [],
        "summary": args.summary or "<一句话摘要>",
        "payload": {},
    }
    out_path = args.out or os.path.join(args.task_dir, "tmp", "event-%s.json" % event["event_id"][:8])
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(event, fh, ensure_ascii=False, indent=2)
    print("✓ 候选事件模板已写入 %s" % out_path)
    print("  预校验: agent_dealer publish --dry-run %s %s" % (args.task_dir, out_path))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    with open(args.event_json, encoding="utf-8") as fh:
        event = json.load(fh)
    if args.dry_run:
        # 与真实 publish 的 auto_previous 行为一致：按当前链尾回填 previous_event_id
        if not args.strict_previous and isinstance(event, dict):
            last = store.last_event()
            event = dict(event)
            event["previous_event_id"] = last["event_id"] if last else None
        report = store.validate(candidate=event)
        print(validator.format_report(report, candidate=True))
        return 0 if report.ok else 1
    published = store.publish(event, owner=args.instance_id,
                              auto_previous=not args.strict_previous)
    print("✓ 事件已发布: %s (%s)" % (published["type"], published["event_id"]))
    return 0


def cmd_artifact_add(args: argparse.Namespace) -> int:
    store = TaskStore(args.task_dir)
    dest = args.dest or os.path.join("artifacts", os.path.basename(args.file))
    staged = store.stage_artifact(os.path.abspath(args.file), dest)
    ref = {
        "path": staged["path"],
        "sha256": staged["sha256"],
        "media_type": args.media_type,
        "version": args.artifact_version,
    }
    _out(ref, True)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    argv = [args.task_dir]
    if args.json:
        argv.append("--json")
    return validator.main(argv)


def cmd_watch(args: argparse.Namespace) -> int:
    from .runner import Runner, load_adapters

    adapters = load_adapters(args.adapters)
    runner = Runner(args.task_dir, adapters, poll_interval=args.interval)

    def on_event(kind: str, data: Any) -> None:
        if kind == "dispatch":
            print("[runner] 已调度: %s" % json.dumps(data, ensure_ascii=False))
        elif kind == "terminal":
            print("[runner] 任务到达终态: %s，停止。" % data.get("status"))

    print("[runner] 监听 %s（每 %ds 全量校验）" % (args.task_dir, args.interval))
    runner.run(on_event=on_event)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent_dealer",
        description="跨模型 Agent 共享目录协作运行时（MMAC）")
    p.add_argument("--version", action="store_true", help="打印版本")
    sub = p.add_subparsers(dest="command")

    def add_actor_flags(sp: argparse.ArgumentParser, role_default: str = "B") -> None:
        sp.add_argument("--role", default=role_default)
        sp.add_argument("--instance-id", default=os.environ.get("MMAC_INSTANCE_ID", "cli-session"))
        sp.add_argument("--provider", default=os.environ.get("MMAC_PROVIDER", "local"))
        sp.add_argument("--client", default=os.environ.get("MMAC_CLIENT", "agent_dealer-cli"))
        sp.add_argument("--model", default=os.environ.get("MMAC_MODEL"))

    sp = sub.add_parser("init", help="创建任务并发布 TASK_CREATED")
    sp.add_argument("task_id")
    sp.add_argument("--title", required=True)
    sp.add_argument("--goal", default="")
    sp.add_argument("--planner", default="A")
    sp.add_argument("--executor", default="B")
    sp.add_argument("--multimodal", default="C")
    sp.add_argument("--reviewer", default="A")
    sp.add_argument("--solo", action="store_true",
                    help="单会话模式：一个角色扮演全部职责（mode=solo，REVIEW_APPROVED 需自证证据）")
    sp.add_argument("--tasks-dir", default="tasks")
    add_actor_flags(sp, "coordinator")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("doctor", help="综合诊断")
    sp.add_argument("task_dir")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("status", help="状态摘要")
    sp.add_argument("task_dir")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("next", help="下一步应由谁行动")
    sp.add_argument("task_dir")
    sp.add_argument("--role", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_next)

    sp = sub.add_parser("claim", help="发布 TASK_CLAIMED 并写入租约")
    sp.add_argument("task_dir")
    sp.add_argument("--subtask-id", default=None)
    sp.add_argument("--summary", default="")
    add_actor_flags(sp, "B")
    sp.set_defaults(func=cmd_claim)

    sp = sub.add_parser("event", help="事件工具")
    sp.add_argument("action", choices=["prepare"])
    sp.add_argument("task_dir")
    sp.add_argument("--type", required=True, choices=validator.EVENT_EXPECTED_STATUS.keys())
    sp.add_argument("--recipient", default="A")
    sp.add_argument("--summary", default="")
    sp.add_argument("--out", default=None)
    add_actor_flags(sp, "B")
    sp.set_defaults(func=cmd_event_prepare)

    sp = sub.add_parser("publish", help="原子发布事件")
    sp.add_argument("task_dir")
    sp.add_argument("event_json")
    sp.add_argument("--dry-run", action="store_true", help="只预校验不发布")
    sp.add_argument("--strict-previous", action="store_true",
                    help="不自动回填 previous_event_id（必须手工填对）")
    sp.add_argument("--instance-id", default=os.environ.get("MMAC_INSTANCE_ID", "cli-session"))
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("artifact", help="产物工具")
    sp.add_argument("action", choices=["add"])
    sp.add_argument("task_dir")
    sp.add_argument("file")
    sp.add_argument("--dest", default=None)
    sp.add_argument("--media-type", default="application/octet-stream")
    sp.add_argument("--version", type=int, default=1, dest="artifact_version")
    sp.set_defaults(func=cmd_artifact_add)

    sp = sub.add_parser("validate", help="校验任务")
    sp.add_argument("task_dir")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("watch", help="Runner 监听调度")
    sp.add_argument("task_dir")
    sp.add_argument("--adapters", required=True, help="adapter JSON 配置路径")
    sp.add_argument("--interval", type=float, default=5.0)
    sp.set_defaults(func=cmd_watch)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", None) is True:
        from . import __version__
        print(__version__)
        return 0
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except MMACError as ex:
        print("✗ " + str(ex))
        return 1
    except json.JSONDecodeError as ex:
        print("✗ [MMAC-E102_INVALID_EVENT] 事件 JSON 解析失败: %s" % ex)
        return 1
    except FileNotFoundError as ex:
        print("✗ [MMAC-E302_ARTIFACT_MISSING] 文件不存在: %s" % ex)
        return 1


if __name__ == "__main__":
    sys.exit(main())

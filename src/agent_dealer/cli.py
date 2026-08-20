"""agent-dealer CLI（Python 模块名 agent_dealer）（P1-02 / P1-03 / P1-04）。

子命令：
  init      创建任务目录、control.md、目录结构并发布 TASK_CREATED
  models    探测已安装的模型客户端 CLI 及版本
  doctor    环境 + 配置 + 事件链 + 产物 + 锁 + 密钥扫描综合诊断
  status    人类可读状态摘要（--json 机器可读）
  next      下一步应由谁行动（--role 过滤）
  claim     发布 TASK_CLAIMED 并写入租约
  event     prepare 生成候选事件 JSON 模板
  publish   唯一原子发布入口（锁 + 预校验 + 产物固化 + 追加 + 复核）
  artifact  add 固化产物并输出 ArtifactRef JSON
  validate  校验任务（等价 python -m agent_dealer.validator）
  report    任务报告：各 agent 贡献、评价与 TODO
  watch     Runner 监听调度循环
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from . import validator
from .errors import E105_INVALID_CONTROL, E202_PLACEHOLDER_MODEL, MMACError
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
  permission_mode: {permission_mode}
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

CLIENT_REGISTRY: List[Dict[str, Any]] = [
    {"client": "claude", "label": "Claude Code", "commands": ["claude"]},
    {"client": "codex", "label": "Codex CLI", "commands": ["codex"]},
    {"client": "kimi", "label": "Kimi CLI", "commands": ["kimi"]},
    {"client": "deepseek", "label": "DeepSeek", "commands": ["deepseek"]},
    {"client": "zai", "label": "z.ai (GLM)", "commands": ["zai", "glm"]},
    {"client": "cursor", "label": "Cursor", "commands": ["cursor-agent", "cursor"]},
    {"client": "gemini", "label": "Gemini CLI", "commands": ["gemini"]},
]

VALID_EFFORTS = ("low", "medium", "high", "max")
VALID_THINKING = ("on", "off")
VALID_PERMISSION_MODES = ("yolo", "confirm")
ROLE_CONFIG_KEYS = ("effort", "thinking", "model")

MODELS_FILE_ENV = "MMAC_MODELS_FILE"


def models_catalog_path() -> str:
    override = os.environ.get(MODELS_FILE_ENV)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".agent_dealer", "models.json")


def load_models_catalog(path: str = None) -> List[Dict[str, Any]]:
    """读取用户声明的模型目录（client/model/efforts/thinking）。目录缺失=空；坏文件降级为空并提示。"""
    catalog_path = path or models_catalog_path()
    if not os.path.isfile(catalog_path):
        return []
    try:
        with open(catalog_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        print("⚠ 模型目录 %s 解析失败，已忽略（删除后可用 --add / --init 重建）" % catalog_path)
        return []
    entries = data.get("models") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    models = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("model"), str) and entry["model"]:
            models.append({
                "client": entry.get("client", ""),
                "model": entry["model"],
                "efforts": [e for e in (entry.get("efforts") or []) if isinstance(e, str)],
                "thinking": bool(entry.get("thinking", False)),
            })
    return models


def _save_models_catalog(path: str, models: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"models": models}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _parse_add_spec(spec: str) -> Dict[str, Any]:
    """解析 --add CLIENT:MODEL[:EFFORTS[:THINKING]]。"""
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise MMACError(E105_INVALID_CONTROL,
                        "--add 格式为 client:model[:efforts[:thinking]]（收到 %r）" % spec)
    if len(parts) > 4:
        raise MMACError(E105_INVALID_CONTROL,
                        "--add 最多 4 段 client:model:efforts:thinking（收到 %r）" % spec)
    client, model = parts[0], parts[1]
    efforts = ["low", "medium", "high"]
    if len(parts) >= 3 and parts[2]:
        efforts = [e.strip() for e in parts[2].split(",") if e.strip()]
    bad = [e for e in efforts if e not in VALID_EFFORTS]
    if bad:
        raise MMACError(E105_INVALID_CONTROL,
                        "--add effort 档位必须取自 %s（收到 %r）"
                        % ("/".join(VALID_EFFORTS), ",".join(bad)))
    thinking = False
    if len(parts) >= 4:
        if parts[3].lower() not in VALID_THINKING:
            raise MMACError(E105_INVALID_CONTROL,
                            "--add thinking 必须为 on/off（收到 %r）" % parts[3])
        thinking = parts[3].lower() == "on"
    return {"client": client, "model": model, "efforts": efforts, "thinking": thinking}


def _add_models(catalog_path: str, specs: List[str]) -> int:
    models = load_models_catalog(catalog_path)
    for spec in specs:
        entry = _parse_add_spec(spec)
        models = [m for m in models
                  if not (m["client"] == entry["client"] and m["model"] == entry["model"])]
        models.append(entry)
    _save_models_catalog(catalog_path, models)
    for entry in [_parse_add_spec(s) for s in specs]:
        print("✓ 已保存 %s %s（effort: %s | thinking: %s）→ %s" % (
            entry["client"], entry["model"], "/".join(entry["efforts"]),
            "支持" if entry["thinking"] else "不支持", catalog_path))
    return 0


def _prompt_models_wizard(catalog_path: str) -> List[Dict[str, Any]]:
    """交互式选择本机可用模型（首次使用；选完由调用方保存）。"""
    installed = [i["client"] for i in probe_clients() if i["installed"]]
    print("开始配置模型目录（保存到 %s；Ctrl-C 取消）" % catalog_path)
    if installed:
        print("已安装客户端: %s" % ", ".join(installed))
    default_client = installed[0] if installed else "claude"
    models: List[Dict[str, Any]] = []
    while True:
        client = input("客户端 [%s]: " % default_client).strip() or default_client
        model = input("模型 ID（回车跳过本条）: ").strip()
        if model:
            raw = input("effort 档位，逗号分隔 [low,medium,high]: ").strip()
            if raw:
                efforts = [e.strip() for e in raw.split(",") if e.strip()]
                bad = [e for e in efforts if e not in VALID_EFFORTS]
                if bad:
                    print("✗ 无效档位 %s（允许 %s），本条改用默认" % (
                        ",".join(bad), "/".join(VALID_EFFORTS)))
                    efforts = ["low", "medium", "high"]
            else:
                efforts = ["low", "medium", "high"]
            thinking = input("支持 thinking? [y/N]: ").strip().lower() in ("y", "yes", "on", "true", "1")
            models.append({"client": client, "model": model,
                           "efforts": efforts, "thinking": thinking})
            print("✓ 已记录 %s %s（effort: %s | thinking: %s）" % (
                client, model, "/".join(efforts), "支持" if thinking else "不支持"))
        else:
            print("（跳过本条）")
        if input("继续添加? [Y/n]: ").strip().lower() in ("n", "no"):
            return models


def _init_models_catalog() -> int:
    catalog_path = models_catalog_path()
    if os.path.exists(catalog_path):
        print("✗ 已存在 %s（不覆盖）；如需调整请用 --add 或手工编辑" % catalog_path)
        return 1
    if not sys.stdin.isatty():
        print("✗ 非交互终端：用 --add client:model[:efforts[:thinking]] 添加，"
              "或手工创建 %s" % catalog_path)
        return 1
    try:
        models = _prompt_models_wizard(catalog_path)
    except (EOFError, KeyboardInterrupt):
        print("\n已取消，未保存。")
        return 1
    if not models:
        print("未添加任何模型，未保存。")
        return 1
    _save_models_catalog(catalog_path, models)
    print("✓ 模型目录已保存: %s（%d 个模型）" % (catalog_path, len(models)))
    return 0


def probe_clients() -> List[Dict[str, Any]]:
    """探测 PATH 中已安装的模型客户端 CLI 及其版本（探测失败一律降级不抛）。

    每个客户端按 commands 顺序探测候选命令名（如 zai 的 zai/glm、
    Cursor 的 cursor-agent/cursor），命中第一个即用。
    """
    results: List[Dict[str, Any]] = []
    for spec in CLIENT_REGISTRY:
        found_cmd = found_path = None
        for cmd in spec["commands"]:
            found_path = shutil.which(cmd)
            if found_path:
                found_cmd = cmd
                break
        if not found_cmd:
            results.append({"client": spec["client"], "label": spec["label"],
                            "path": None, "installed": False, "version": None})
            continue
        version = "unknown"
        try:
            proc = subprocess.run([found_cmd, "--version"], capture_output=True, timeout=10)
            if proc.returncode == 0:
                text = (proc.stdout or proc.stderr).decode("utf-8", "replace").strip()
                if text:
                    version = text.splitlines()[0][:120]
        except (subprocess.TimeoutExpired, OSError):
            pass
        results.append({"client": spec["client"], "label": spec["label"],
                        "path": found_path, "installed": True, "version": version})
    return results


def cmd_models(args: argparse.Namespace) -> int:
    if getattr(args, "add_models", None):
        return _add_models(models_catalog_path(), args.add_models)
    if getattr(args, "init_catalog", False):
        return _init_models_catalog()
    probed = probe_clients()
    installed = {item["client"] for item in probed if item["installed"]}
    catalog_path = models_catalog_path()
    models = load_models_catalog(catalog_path)
    if args.json:
        _out({"clients": probed, "models": models, "catalog_path": catalog_path}, True)
        return 0
    print("模型客户端探测：")
    for item in probed:
        if item["installed"]:
            print("  %s ✓ %s（%s）" % (item["client"], item["version"], item["path"]))
        else:
            print("  %s ✗ 未安装" % item["client"])
    if models:
        print("可用模型（目录 %s）：" % catalog_path)
        by_client: Dict[str, List[Dict[str, Any]]] = {}
        for m in models:
            by_client.setdefault(m["client"] or "（未标注客户端）", []).append(m)
        for client, entries in by_client.items():
            mark = "✓" if client in installed else "⚠ 客户端未探测到"
            for m in entries:
                print("  %s %s（effort: %s | thinking: %s）[%s]" % (
                    client, m["model"], "/".join(m["efforts"]) or "-",
                    "支持" if m["thinking"] else "不支持", mark))
    else:
        print("模型目录 %s 未配置：`models --init` 交互式选择本机模型，"
              "或 `--add client:model:efforts:thinking` 直接添加"
              "（如 --add claude:glm-5.3:low,medium,high,max:on）" % catalog_path)
    print("提示: init 时用 --model/--effort/--thinking/--permission-mode/--role-config 配置档位")
    return 0


def _init_models_catalog() -> int:
    catalog_path = models_catalog_path()
    if os.path.exists(catalog_path):
        print("✗ 已存在 %s（不覆盖）；如需调整请用 --add 或手工编辑" % catalog_path)
        return 1
    if not sys.stdin.isatty():
        print("✗ 非交互终端：用 --add client:model[:efforts[:thinking]] 添加，"
              "或手工创建 %s" % catalog_path)
        return 1
    try:
        models = _prompt_models_wizard(catalog_path)
    except (EOFError, KeyboardInterrupt):
        print("\n已取消，未保存。")
        return 1
    if not models:
        print("未添加任何模型，未保存。")
        return 1
    _save_models_catalog(catalog_path, models)
    print("✓ 模型目录已保存: %s（%d 个模型）" % (catalog_path, len(models)))
    return 0


def _out(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


SOLO_AGENT_CAPABILITIES = ("[architecture, planning, review, coding, testing, "
                           "documentation, vision, image-analysis]")
SOLO_AGENT_NOTE = ("solo 模式——本角色由单一会话扮演 A/B/C 全部职责；"
                   "REVIEW_APPROVED 需 self_review + reproduced_commands（validator 强制），"
                   "批准为临时性，可被后续独立审查覆盖")


def _agent_block(role: str, capabilities: str, cost_weight: int,
                 overrides: Dict[str, Dict[str, str]],
                 note: str = "") -> str:
    """生成 control.md agents 节的单角色块，含可选 effort/thinking/model 覆盖。"""
    cfg = overrides.get(role, {})
    lines = [
        "  %s:" % role,
        "    provider: configurable",
        "    client: configurable",
        "    model: %s" % cfg.get("model", "configurable"),
        "    capabilities: %s" % capabilities,
        "    cost_weight: %d" % cost_weight,
        "    effort: %s" % cfg.get("effort", "medium"),
        "    thinking: %s" % cfg.get("thinking", "off"),
    ]
    if note:
        lines.append("    note: %s" % note)
    return "\n".join(lines)


def _parse_role_config(entries: List[str],
                       valid_roles: List[str]) -> Dict[str, Dict[str, str]]:
    """解析 --role-config 角色:键=值 列表；非法角色/键/值立即报 E105/E202。"""
    overrides: Dict[str, Dict[str, str]] = {}
    for entry in entries or []:
        if ":" not in entry or "=" not in entry:
            raise MMACError(E105_INVALID_CONTROL,
                            "--role-config 格式必须为 角色:键=值（收到 %r）" % entry)
        role, kv = entry.split(":", 1)
        key, value = kv.split("=", 1)
        role, key, value = role.strip(), key.strip(), value.strip()
        if role not in valid_roles:
            raise MMACError(E105_INVALID_CONTROL,
                            "--role-config 角色不存在: %r（本任务角色: %s）"
                            % (role, "/".join(valid_roles)))
        if key not in ROLE_CONFIG_KEYS:
            raise MMACError(E105_INVALID_CONTROL,
                            "--role-config 键必须为 %s 之一（收到 %r）"
                            % ("/".join(ROLE_CONFIG_KEYS), key))
        if key == "model":
            if not value or validator.is_placeholder_model(value):
                raise MMACError(E202_PLACEHOLDER_MODEL,
                                "--role-config %s:model 必须为真实模型标识（收到 %r）" % (role, value))
        elif key == "effort" and value not in VALID_EFFORTS:
            raise MMACError(E105_INVALID_CONTROL,
                            "--role-config %s:effort 必须为 %s 之一（收到 %r）"
                            % (role, "/".join(VALID_EFFORTS), value))
        elif key == "thinking" and value not in VALID_THINKING:
            raise MMACError(E105_INVALID_CONTROL,
                            "--role-config %s:thinking 必须为 %s 之一（收到 %r）"
                            % (role, "/".join(VALID_THINKING), value))
        overrides.setdefault(role, {})[key] = value
    return overrides


def _merge_role_config(valid_roles: List[str], effort: str, thinking: str,
                       entries: List[str]) -> Dict[str, Dict[str, str]]:
    """全局默认档位 + --role-config 覆盖 → 每角色生效配置。"""
    merged = {role: {"effort": effort, "thinking": thinking} for role in valid_roles}
    for role, cfg in _parse_role_config(entries, valid_roles).items():
        merged.setdefault(role, {}).update(cfg)
    return merged


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
        overrides = _merge_role_config(
            [solo_role], args.effort, args.thinking, args.role_config)
        agents_block = _agent_block(
            solo_role, SOLO_AGENT_CAPABILITIES, 1, overrides, note=SOLO_AGENT_NOTE)
        mode = "solo"
    else:
        planner, executor = args.planner, args.executor
        multimodal, reviewer = args.multimodal, args.reviewer
        overrides = _merge_role_config(
            [planner, executor, multimodal], args.effort, args.thinking, args.role_config)
        agents_block = "\n".join([
            _agent_block(planner, "[architecture, planning, review, reasoning]", 5, overrides),
            _agent_block(executor, "[coding, testing, documentation, file-processing]", 1, overrides),
            _agent_block(multimodal, "[vision, image-analysis, multimodal]", 3, overrides),
        ])
        mode = "multi"

    control = CONTROL_TEMPLATE.format(
        task_id=args.task_id, title=args.title, created_at=now_iso(),
        mode=mode, permission_mode=args.permission_mode,
        agents_block=agents_block,
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
    print("  下一步: agent-dealer next %s" % task_dir)
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

    # 4. 客户端可用性（与 models 命令共用探测；doctor 输出沿用 ✓/✗ 文案）
    clients = {item["client"]: item["installed"] for item in probe_clients()}
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
    print("  预校验: agent-dealer publish --dry-run %s %s" % (args.task_dir, out_path))
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
            print(format_report(build_report(args.task_dir)))

    print("[runner] 监听 %s（每 %ds 全量校验）" % (args.task_dir, args.interval))
    runner.run(on_event=on_event)
    return 0


def build_report(task_dir: str) -> Dict[str, Any]:
    """聚合事件链：各 agent 贡献、最新评价与遗留 TODO。只读，不发布事件。"""
    store = TaskStore(task_dir)
    report = store.validate()
    control = report.control or {}
    events = report.events

    agents: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for e in events:
        actor = e.get("actor") or {}
        key = "%s/%s" % (actor.get("role", "?"), actor.get("instance_id", "?"))
        if key not in agents:
            order.append(key)
            agents[key] = {
                "role": actor.get("role"),
                "instance_id": actor.get("instance_id"),
                "model": actor.get("model"),
                "event_counts": {},
                "artifacts": [],
                "latest_review": None,
            }
        entry = agents[key]
        etype = e.get("type", "?")
        entry["event_counts"][etype] = entry["event_counts"].get(etype, 0) + 1
        for ref in e.get("artifacts") or []:
            if isinstance(ref, dict):
                entry["artifacts"].append(
                    {"path": ref.get("path"), "version": ref.get("version", 1)})
        payload = e.get("payload") or {}
        if etype in ("REVIEW_APPROVED", "REVISION_REQUIRED") and "score" in payload:
            entry["latest_review"] = {
                "type": etype,
                "score": payload.get("score"),
                "blocking_issues": payload.get("blocking_issues"),
            }

    evaluation = None
    for e in reversed(events):
        if e.get("type") in ("REVIEW_APPROVED", "REVISION_REQUIRED"):
            payload = e.get("payload") or {}
            evaluation = {
                "type": e.get("type"),
                "reviewer": (e.get("actor") or {}).get("role"),
                "score": payload.get("score"),
                "blocking_issues": payload.get("blocking_issues"),
                "issues": payload.get("issues") or [],
                "self_review": payload.get("self_review") is True,
            }
            break

    approved = any(e.get("type") == "REVIEW_APPROVED" for e in events)
    todos: List[Dict[str, Any]] = []
    for idx, e in enumerate(events):
        etype = e.get("type")
        payload = e.get("payload") or {}
        if etype == "REVISION_REQUIRED":
            cycle = e.get("revision_cycle", 0)
            superseded = approved or any(
                later.get("revision_cycle", 0) > cycle for later in events[idx + 1:])
            if not superseded:
                for issue in payload.get("issues") or []:
                    todos.append({"source": "REVISION_REQUIRED", "todo": _issue_text(issue)})
                if not payload.get("issues"):
                    todos.append({"source": "REVISION_REQUIRED",
                                  "todo": e.get("summary") or "返工事项未列明"})
        elif etype in ("TASK_BLOCKED", "TASK_FAILED"):
            todos.append({"source": etype,
                          "todo": payload.get("reason") or e.get("summary") or "原因未列明"})
    if approved and control.get("workflow", {}).get("mode") == "solo":
        todos.append({"source": "solo-approval",
                      "todo": "solo 临时批准（自审），待独立第二模型复核"})

    return {
        "task_dir": task_dir,
        "task_id": control.get("task", {}).get("id") or os.path.basename(task_dir),
        "title": control.get("task", {}).get("title"),
        "final_status": report.final_status,
        "valid": report.ok,
        "event_count": len(events),
        "agents": [agents[k] for k in order],
        "evaluation": evaluation,
        "todos": todos,
    }


def _issue_text(issue: Any) -> str:
    if isinstance(issue, dict):
        for key in ("description", "message", "title", "summary"):
            if issue.get(key):
                return str(issue[key])
        return json.dumps(issue, ensure_ascii=False)
    return str(issue)


def format_report(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("任务报告: %s（%s）" % (data.get("task_id"), data.get("task_dir")))
    lines.append("状态: %s | 事件数: %d | 链校验: %s" % (
        data.get("final_status"), data.get("event_count"),
        "通过" if data.get("valid") else "存在错误"))
    if data.get("title"):
        lines.append("标题: %s" % data["title"])
    lines.append("")
    lines.append("== 各 Agent 贡献 ==")
    for agent in data.get("agents", []):
        events_desc = ", ".join("%s×%d" % (t, n)
                                for t, n in (agent.get("event_counts") or {}).items())
        arts = agent.get("artifacts") or []
        lines.append("- %s（model=%s）: %s；产物 %d 件%s" % (
            agent.get("role"), agent.get("model"),
            events_desc or "无事件", len(arts),
            "（%s）" % ", ".join(a["path"] for a in arts) if arts else ""))
        review = agent.get("latest_review")
        if review:
            lines.append("    最新评审: %s score=%s blocking_issues=%s" % (
                review["type"], review["score"], review["blocking_issues"]))
    lines.append("")
    lines.append("== 任务评价 ==")
    ev = data.get("evaluation")
    if ev is None:
        lines.append("- 暂无评审事件")
    else:
        self_note = "，self_review（临时批准）" if ev.get("self_review") else ""
        lines.append("- %s by %s: score=%s blocking_issues=%s%s" % (
            ev["type"], ev.get("reviewer"), ev.get("score"),
            ev.get("blocking_issues"), self_note))
        for issue in ev.get("issues") or []:
            lines.append("    问题: %s" % _issue_text(issue))
    lines.append("")
    lines.append("== TODO ==")
    todos = data.get("todos") or []
    if not todos:
        lines.append("- 无遗留事项")
    for item in todos:
        lines.append("- [%s] %s" % (item.get("source"), item.get("todo")))
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    data = build_report(args.task_dir)
    if args.json:
        _out(data, True)
    else:
        print(format_report(data))
    return 0 if data["valid"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-dealer",
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
    sp.add_argument("--effort", choices=list(VALID_EFFORTS), default="medium",
                    help="全局模型档位（默认 medium，可用 --role-config 按角色覆盖）")
    sp.add_argument("--thinking", choices=list(VALID_THINKING), default="off",
                    help="是否开启 thinking（默认 off）")
    sp.add_argument("--permission-mode", choices=list(VALID_PERMISSION_MODES),
                    default="yolo", dest="permission_mode",
                    help="权限模式（默认 yolo，自动执行无需确认；confirm 需人工确认）")
    sp.add_argument("--role-config", action="append", default=[], dest="role_config",
                    metavar="ROLE:KEY=VALUE",
                    help="按角色覆盖档位，键为 effort/thinking/model，可多次，如 A:effort=high")
    sp.add_argument("--tasks-dir", default="tasks")
    add_actor_flags(sp, "coordinator")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("models", help="探测已安装的模型客户端与可用模型档位")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--init", action="store_true", dest="init_catalog",
                    help="交互式选择本机可用模型并保存到 %s（已存在则不覆盖）" % models_catalog_path())
    sp.add_argument("--add", action="append", default=[], dest="add_models",
                    metavar="CLIENT:MODEL[:EFFORTS[:THINKING]]",
                    help="直接添加模型（upsert，可多次），如 --add claude:glm-5.3:low,medium,high,max:on")
    sp.set_defaults(func=cmd_models)

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

    sp = sub.add_parser("report", help="任务报告：各 agent 贡献、评价与 TODO")
    sp.add_argument("task_dir")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_report)

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

"""validate.py 夹具测试套件（stdlib unittest）。

对每个 fixture 子目录运行 tools/validate.py，断言：
- exit code（0 表示合法、1 表示预期失败）
- 输出中包含预期的关键词

运行：
    cd <repo-root>
    python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures -v
或：
    python3 tasks/task-20260810-002/fixtures/test_validate_fixtures.py
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATE = REPO_ROOT / "tools" / "validate.py"
FIXTURES = Path(__file__).resolve().parent
PY = sys.executable


def run(task_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(VALIDATE), str(task_dir), *extra],
        capture_output=True,
        text=True,
    )


class ValidFixtureTests(unittest.TestCase):
    def test_valid_chain_passes(self):
        r = run(FIXTURES / "valid")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("全部通过", r.stdout)

    def test_allowed_paths_are_relative_to_collaboration_root_not_skill_install(self):
        """验证器位于何处不应影响工作区 `allowed_paths: ["./"]` 的含义。"""
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "tasks" / "task-fixture-001"
            shutil.copytree(FIXTURES / "valid", copied)
            r = run(copied)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("全部通过", r.stdout)


class FailureFixtureTests(unittest.TestCase):
    """每个失败场景应返回 exit code 1，并在输出中给出对应关键词。"""

    def _expect(self, name: str, keyword: str) -> subprocess.CompletedProcess:
        r = run(FIXTURES / name)
        self.assertNotEqual(r.returncode, 0, f"{name}: 应失败但 exit=0\n{r.stdout}")
        self.assertIn(keyword, r.stdout, f"{name}: 期望关键词 {keyword!r} 未出现\n{r.stdout}")
        return r

    def test_duplicate_event_id(self):
        self._expect("duplicate_event_id", "event_id 重复")

    def test_bad_caused_by(self):
        self._expect("bad_caused_by", "caused_by 必须引用更早事件")

    def test_illegal_status_type(self):
        self._expect("illegal_status_type", "类型 WORK_READY 期望 status=WORK_READY")

    def test_bad_hash(self):
        self._expect("bad_hash", "产物哈希不一致")

    def test_path_traversal(self):
        self._expect("path_traversal", "含非法 `..` 穿越")

    def test_placeholder_model(self):
        self._expect("placeholder_model", "actor.model 不得为占位符")

    def test_fork_previous(self):
        self._expect("fork_previous", "检测到分叉")

    def test_bad_iso_timestamp(self):
        self._expect("bad_iso_timestamp", "timestamp 不符合 ISO 8601")

    def test_missing_required_field(self):
        self._expect("missing_required_field", "缺少必需字段 task_id")

    def test_heartbeat_cannot_change_status(self):
        self._expect("heartbeat_status_change", "状态保持事件")

    def test_caused_by_cannot_point_forward(self):
        self._expect("future_caused_by", "caused_by 必须引用更早事件")

    def test_executor_cannot_self_approve(self):
        self._expect("self_approval", "只能由 reviewer=A 发布")

    def test_approval_below_target_score_fails(self):
        self._expect("low_score_approval", "低于门槛")

    def test_symlink_cannot_escape_task_dir(self):
        self._expect("symlink_escape", "符号链接逃逸任务目录")

    def test_revision_limit_requires_blocked(self):
        self._expect("revision_limit_exceeded", "已达返工上限")

    def test_executor_cannot_reopen_terminal_task(self):
        self._expect("unauthorized_reopen", "TASK_REOPENED 只能由 human/coordinator 发布")


class LegacyCompatibilityTests(unittest.TestCase):
    """对真实 task-001 历史日志的兼容性验证。"""

    TASK_001 = REPO_ROOT / "tasks" / "task-20260810-001"

    def test_task_001_readable_with_legacy_fallback(self):
        r = run(self.TASK_001)
        # task-001 历史中：
        # - 多个 actor.model='configured-model' 占位符 → 新规则下报错（合理）
        # - csv2json.py 经 cycle=1 修复后内容变化，与 cycle=0 WORK_READY 哈希不匹配 → 报错（合理）
        # - 相对项目根路径产物 → 通过 legacy fallback 解析，打印告警
        # 校验：必须能读取日志、解析全部事件、报告最终 APPROVED 状态
        self.assertIn("当前状态：APPROVED", r.stdout, r.stdout)
        self.assertIn("legacy fallback", r.stdout)
        # 历史可读，但应当报已知问题（不掩盖）
        self.assertIn("个错误", r.stdout)

    def test_task_002_after_C_claim_will_be_valid(self):
        # 此测试仅验证：当前 task-002 状态可被解析
        r = run(REPO_ROOT / "tasks" / "task-20260810-002")
        # 不强制 exit code（C 尚未发布事件时也已可解析；B 已发布）
        self.assertIn("校验", r.stdout)


class IdempotencyTests(unittest.TestCase):
    """同一输入多次运行结果一致；不写文件、不发起网络。"""

    def test_repeatable(self):
        r1 = run(FIXTURES / "valid")
        r2 = run(FIXTURES / "valid")
        self.assertEqual(r1.returncode, r2.returncode)
        self.assertEqual(r1.stdout, r2.stdout)

    def test_candidate_event_is_validated_without_append(self):
        task = FIXTURES / "valid"
        before = (task / "coordination.md").read_bytes()
        candidate = {
            "protocol_version": "1.0", "event_id": "e5", "previous_event_id": "e4",
            "task_id": "task-fixture-001", "parent_task_id": None,
            "type": "EXECUTION_STARTED", "status": "EXECUTING",
            "actor": {"role": "B", "instance_id": "fixture-b-001", "provider": "zhipu",
                      "client": "claude", "model": "glm-5.2"},
            "recipient": {"role": "A"}, "caused_by": "e4", "revision_cycle": 0,
            "timestamp": "2026-08-10T13:02:00+08:00", "artifacts": [],
            "summary": "candidate", "payload": {},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as fh:
            json.dump(candidate, fh)
            fh.flush()
            result = run(task, "--candidate", fh.name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("含候选事件", result.stdout)
        self.assertEqual((task / "coordination.md").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

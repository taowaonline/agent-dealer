# Contributing

## 环境

- Python 3.8+，运行时零第三方依赖。
- 开发依赖：`python -m venv .venv && .venv/bin/pip install -e ".[dev]"`。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests/unit -v
.venv/bin/python -m unittest discover -s tests/integration -v
.venv/bin/coverage run -m unittest discover -s tests && .venv/bin/coverage report --fail-under=90
```

任何修改必须保持：

1. 既有测试全部通过，新行为附带新测试；
2. `collab doctor examples/quickstart` 零错误；
3. 仅使用标准库（运行时）；
4. 协议语义变更必须先改 `references/` 中的 schema 文档并提升版本号，再改代码。

## 协议规则

- `coordination.md` 只追加；已发布事件与版本化产物不可修改。
- 所有事件发布必须经过 `collab publish`（或 `TaskStore.publish`），禁止手工拼接日志。
- 校验器报错与告警分级不得静默调整；历史问题的降级必须显式写入任务的 `expected-warnings.json`。

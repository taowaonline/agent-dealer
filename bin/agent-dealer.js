#!/usr/bin/env node
/**
 * agent-dealer 启动 shim：
 * 定位 Python >= 3.9（python3 / python，Windows 走 py -3），
 * 以包内 src/ 为 PYTHONPATH 运行 agent_dealer CLI，透传参数、TTY 与退出码。
 * 本文件零依赖，纯 Node 标准库。
 */
'use strict';

const { spawnSync } = require('child_process');
const path = require('path');

const srcDir = path.join(__dirname, '..', 'src');
const args = process.argv.slice(2);

const env = Object.assign({}, process.env);
env.PYTHONPATH = srcDir + (env.PYTHONPATH ? path.delimiter + env.PYTHONPATH : '');

const candidates = process.platform === 'win32'
  ? [['py', '-3'], ['python']]
  : [['python3'], ['python']];

let lastError = null;
for (const cmd of candidates) {
  const full = cmd.slice(1).concat(['-m', 'agent_dealer'], args);
  const result = spawnSync(cmd[0], full, { stdio: 'inherit', env });
  if (result.error) {
    lastError = result.error;
    continue;
  }
  process.exit(result.status === null ? 1 : result.status);
}

console.error('agent-dealer: 未找到可用的 Python（需要 Python >= 3.9）。');
console.error('请安装 Python 后重试：https://www.python.org/downloads/');
if (lastError) {
  console.error(String(lastError));
}
process.exit(127);

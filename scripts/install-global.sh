#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
install_root=${AGENT_DEALER_HOME:-"$HOME/.local/share/agent_dealer"}
bin_dir=${AGENT_DEALER_BIN_DIR:-"$HOME/.local/bin"}
python_bin=${PYTHON:-python3}
venv_dir="$install_root/venv"

mkdir -p "$install_root" "$bin_dir"
"$python_bin" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --disable-pip-version-check --upgrade "$project_root"

for command_name in agent_dealer collab; do
    source_path="$venv_dir/bin/$command_name"
    target_path="$bin_dir/$command_name"
    if [ -e "$target_path" ] && [ ! -L "$target_path" ]; then
        echo "拒绝覆盖已有普通文件: $target_path" >&2
        exit 1
    fi
    ln -sfn "$source_path" "$target_path"
done

# 清理 v0.2.0 初版曾创建的连字符命令；仅删除指向本安装目录的 symlink。
legacy_hyphen_command="$bin_dir/agent-dealer"
if [ -L "$legacy_hyphen_command" ] && [ "$(readlink "$legacy_hyphen_command")" = "$venv_dir/bin/agent-dealer" ]; then
    unlink "$legacy_hyphen_command"
fi

echo "Agent Dealer 已安装: $bin_dir/agent_dealer"
case ":${PATH:-}:" in
    *":$bin_dir:"*) ;;
    *) echo "请将 $bin_dir 加入 PATH 后重开终端。" ;;
esac

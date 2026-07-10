# Claude Code 护栏（Guardrails）

PreToolUse hooks，在 Bash 命令执行前自动检查，拦截危险操作。

## 结构

```
claude/
├── settings.json                  # 注册 hook
├── hooks/
│   ├── block-dangerous-git.sh     # 拦截危险 git 命令
│   └── block-remote-edit.sh       # 拦截 SSH 远程修改
└── docs/
    └── guardrails.md              # 本文档
```

## 依赖

**python3** — 用于解析 Claude Code 传入的 JSON 输入。

> 需要确保系统已安装 python3。没有用 `jq` 因为它不在所有服务器上可用。

## 护栏规则

### block-dangerous-git.sh

拦截以下命令：

| 命令 | 原因 |
|------|------|
| `git reset --hard` | 不可逆，会丢失未提交的改动 |
| `git clean -fd` / `git clean -f` | 删除所有未跟踪文件 |
| `git branch -D` | 强制删除分支，无法恢复 |
| `git checkout .` / `git restore .` | 丢弃所有工作区改动 |
| `push --force` | 覆盖远程历史 |

### block-remote-edit.sh

核心原则：**只允许通过 scp 拉取 + 本地编辑 + scp 推送的工作流，禁止直接在远程服务器上修改文件。**

| 操作 | 行为 |
|------|------|
| `ssh host`（交互登录） | 放行 |
| `ssh host "cat/grep/tail/..."`（只读查询） | 放行 |
| `ssh host "sed -i/vim/rm/..."`（修改文件） | **阻断** |
| `ssh host "systemctl restart"`（运维写操作） | **阻断** |
| `ssh host "<未知命令>"` | **阻断**（fail-safe） |
| `scp host:path ./local`（拉取） | 放行 |
| `scp ./local host:path`（推送） | **阻断**（需确认） |

检查顺序：修改模式 → 只读模式 → 默认阻断。

## Hook 工作原理

1. Claude Code 在执行 Bash 命令前，将命令信息以 JSON 格式写入 hook 的 stdin
2. Hook 用 python3 解析 JSON，提取 `tool_input.command`
3. 正则匹配判断是否危险
4. `exit 0` = 放行，`exit 2` = 阻断（stderr 信息会展示给用户）
5. 被阻断的命令可以手动确认后重新执行

## 部署

```bash
# 项目级别（提交到 git）
cp claude/hooks/* ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh

# 全局 settings.json 中注册：
# "hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [...] } ] }
```

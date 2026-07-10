# AGENTS.md

本仓库通过 GitHub Issues + Pull Requests 管理所有变更。

## 工作流

1. 每个任务对应一个 GitHub Issue
2. AI Agent 从 Issue 切 `feature/XX-description` 分支进行修改
3. 修改完成后开 PR，代码保持简洁，**不在代码中写解释性注释**
4. PR 提交后，**必须用 `gh pr-review` 在每处改动旁添加 inline review comment**，说明为什么这么改（不用 `_split_preserving_fences` 直接 split、为什么 /retry 例外等）
5. 用户 review diff 和注释，满意后 Merge

## PR 必须包含

- **测试方法**：明确写出如何在服务器上测试该改动（ssh 命令、预期行为、怎么看结果）
- **回滚方案**：如果出问题怎么恢复（git revert、cp 备份文件等）
- 关联的 Issue 编号（`Closes #N`）

## 代码规范

- Python 代码保持与上游 Hermes 一致的风格
- 不改动上游的已有逻辑，新增代码用独立函数/方法
- 环境变量统一从 `os.getenv()` 读取，不硬编码
- `.env` 不进 git，用 `.env.example` 做模板
- config 文件（`config.yaml`、`honcho.json`）可直接跟踪

## 目录说明

```
hermes/upstream/   ← 官方源码（hermes update 后更新）
hermes/modified/   ← 修改后的源码（= 服务器上跑的）
hermes/docs/       ← 每个功能一篇文档
hermes/config/     ← 配置文件
plugins/           ← 自制插件
infra/             ← VPS 基础设施
pc-setup/          ← PC 折腾文档
scripts/           ← 部署脚本
```

## 部署

```bash
ssh root@10.10.10.1 "cd ~/hq && git pull && bash scripts/deploy.sh"
```

## 分支保护

`main` 分支受 Ruleset 保护：必须通过 PR 合并，禁止 force push，禁止删除。

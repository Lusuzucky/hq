# 部署脚本设计

## 两个脚本

| 脚本 | 用途 | 时机 | 发现方式 |
|------|------|------|----------|
| `deploy.sh` | 全量部署 | 合并到 main 后 | `find` 遍历 `modified/` 和 `plugins/` 下全部文件 |
| `deploy-test.sh` | 测试部署 + 可回滚 | feature 分支测试 | `git diff origin/main...HEAD` 自动检测本分支改动 |

不需要手动维护文件列表。

## 为什么这么设计

### 第一版（手写 FILES 数组）

每个 feature 分支编辑 `deploy-test.sh`，在 `FILES` 数组里手写要部署的文件。合并前还原模板。

**问题：**
- 漏写/多写文件
- 忘记还原模板就合入 main
- `pc_utils.py` 部署到两个目录只能手写两次
- 多次部署后备份逻辑复杂

### 第二版（git diff 自动检测）

`git diff main...HEAD --name-only` 自动发现本分支改动的文件。

**解决的问题：**
- 精确知道改了哪些文件
- 不需要手写、不会漏、不会多

**新问题：**
- `main` 是本地引用，服务器可能没 fetch，变成 stale 比较
- 改为 `git fetch origin main && git diff origin/main...HEAD`

### 第三版（备份用完整路径做 key）

**问题：** 第一版备份用 `basename` 做文件名。多个目录有同名文件（如 `__init__.py`、`pc_utils.py`），回滚时会全匹配，同一个备份文件被恢复到所有同名目标。

**修复：** 用完整目标路径（`/` 替换为 `_`）做 key，确保唯一。

### 第四版（deploy.sh find 路径匹配 bug）

**问题：** `find "$REPO_DIR/..."` 返回绝对路径（`/root/hq/hermes/modified/tools/tts_tool.py`），但 `case` 匹配用相对路径（`hermes/modified/tools/*`），全跳过不部署。

**修复：** `rel="${f#$REPO_DIR/}"` 砍掉前缀再匹配。

## 回滚机制

`deploy-test.sh --rollback` 两步：

1. 还原备份：`.orig_files` 记录 `safename|target`，按记录恢复
2. 删除新增：`.new_files` 记录部署前不存在的文件，回滚时删掉

**关键安全点：** 只备份第一次——后续多次部署不会覆盖首次备份，回滚始终回到部署前的干净状态。

## 路径映射

`map_targets()` 函数维护 repo 路径 → 安装路径的映射，`deploy.sh` 和 `deploy-test.sh` 共享同一份映射逻辑。新增文件时两边自动生效，只需加一条 `case`。

```bash
hermes/modified/tools/* → /usr/local/lib/hermes-agent/tools/
plugins/gptsovits/*     → ~/.hermes/profiles/gf/plugins/tts/gptsovits/
plugins/pc_utils.py     → 部署到 tts/ 和 image_gen/ 两个目录
```

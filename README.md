# homelab

Hermes Agent 定制 + PC 基础设施配置的集中管理仓库。

## 目录结构

```
homelab/
├── README.md
│
├── hermes/
│   ├── upstream/              # 干净的 Hermes 官方源码（hermes update 后拷贝）
│   ├── modified/              # 修改后的源码（≈ 服务器 /usr/local/lib/hermes-agent/ 下跑的文件）
│   ├── docs/                  # 每个功能一篇文档（编号+描述）
│   └── skills/                # Agent skill 文件（部署到 ~/.hermes/profiles/gf/skills/）
│
├── plugins/                   # 自制插件（部署到 ~/.hermes/profiles/gf/plugins/）
│   ├── pc_utils.py            # WOL 共享模块
│   ├── comfyui/               # ComfyUI image_gen 插件
│   └── gptsovits/             # GPT-SoVITS TTS 插件
│
├── infra/                     # VPS 基础设施（胶水层）
│   ├── proxy/                 # ollama / honcho 透明代理
│   ├── wol-server/            # WOL 监听服务
│   └── systemd/               # systemd unit 文件
│
├── pc-setup/                  # PC 折腾文档
│   ├── wol.md
│   ├── openwrt.md
│   ├── autosuspend.md
│   ├── build-log.md
│   └── failures/
│
└── scripts/
    └── deploy.sh
```

## 工作流

### 分支策略

- **`main` 分支受保护，禁止直接 push**。所有改动必须走 feature 分支 + PR。

```
main            ← 稳定版（= 服务器上跑着的）
feature/xxx     ← 每个改动一个分支，测试通过后 PR 合并入 main
```

### 日常操作

```bash
# 1. 从 main 切出新分支
git checkout main && git pull
git checkout -b feature/wol-timeout-fix

# 2. 改代码，commit
git commit -am "wol: 增加超时重试逻辑"

# 3. push 并开 PR
git push -u origin feature/wol-timeout-fix
# → 在 GitHub 上开 PR，自己 review diff

# 4. review 通过后合并到 main
# → GitHub 上点 Merge

# 5. 删除分支（可选）
git branch -d feature/wol-timeout-fix
```

### 服务器部署

```bash
# 服务器上（首次需要 clone）：
cd ~/homelab && git pull

# 复制到 Hermes 安装目录：
cp hermes/modified/*.py /usr/local/lib/hermes-agent/gateway/platforms/qqbot/
cp hermes/modified/*.py /usr/local/lib/hermes-agent/gateway/platforms/
cp hermes/modified/*.py /usr/local/lib/hermes-agent/

# 重启：
hermes gateway restart -p gf
```

### Hermes 升级流程

```bash
# 1. 备份当前 upstream
cp -r hermes/upstream hermes/upstream.old

# 2. 复制新版 Hermes 官方源码到 upstream/
hermes update  # 恢复官方状态
cp /usr/local/lib/hermes-agent/...  hermes/upstream/

# 3. 查看每个文件的变更
git diff hermes/upstream/adapter.py hermes/modified/adapter.py

# 4. 手动合并冲突，更新 modified/
# 5. commit + PR + 部署
```

## 修改登记表

每项修改必须：有文档（`docs/` 下），有对应代码（`modified/` 下），有 git commit 记录。

| # | 功能 | 涉及文件 | 状态 |
|---|------|---------|------|
| 01 | 段落自动分割 + 打字延迟 | `adapter.py`, `base.py`, `send_message_tool.py` | ✅ |
| 02 | TTS 情感参数透传 | `tts_tool.py`, `gptsovits/__init__.py` | ✅ |
| 04 | 部署脚本（全量 + 测试回滚） | `scripts/deploy.sh`, `scripts/deploy-test.sh` | ✅ |
| — | idle-nudge 空闲提醒 | — | 待开发 |
| — | auto-continue 自动继续 | — | 待开发 |
| — | message-coalesce 消息合并 | — | 待开发 |
| 08 | media-extraction 媒体标签提取 | `adapter.py` | ✅ |
| — | silent-skip 静默跳过 | — | 待开发 |
| — | WOL 网络唤醒 | — | 待开发 |
| — | 首条消息注入 | — | 待开发 |

*Hermes update 后逐项重新登记。*

## 多机协作

三台机器（Windows PC、笔记本、Linux VPS）都会编辑代码。

**唯一真相源 = GitHub。** 任何一台机器改代码的流程：

```bash
git pull                    # 先拉最新
git checkout -b feature/xxx # 切分支
# 改代码...
git commit -am "..."
git push                    # 推到 GitHub
```

**在服务器上直接测试改了代码？** 测试完必须 commit + push，不能留在本地。

```bash
# 服务器上测试完后：
git status                  # 看看改了哪些
git diff                    # review 一遍
git commit -am "fix: ..."   # 存档
git push                    # 上传
```

这样其他机器 pull 就能拿到最新改动，不会被覆盖。

# Honcho Dream 与 autosuspend 适配

## 问题

synbox 上 autosuspend 每 5 分钟无活动即挂起系统。Dream 的空闲定时器使用
`CLOCK_MONOTONIC`（`asyncio.sleep`），挂起期间不计时，导致 dream 在频繁
挂起的机器上永远无法触发。

## 改动

### 1. `DREAM_IDLE_TIMEOUT_MINUTES=4`（.env）

在 autosuspend 5 分钟前触发 dream，抢在系统挂起之前运行。

### 2. 空闲定时器使用墙钟时间（dream_scheduler.py）

```python
# 之前：asyncio.sleep（monotonic，suspend 不计时）
await asyncio.sleep(delay_minutes * 60)

# 之后：time.time() 墙钟（suspend 也计时，恢复后立即检查）
deadline = time_module.time() + delay_minutes * 60
while time_module.time() < deadline:
    await asyncio.sleep(min(10, deadline - time_module.time()))
```

### 3. Dream 期间阻止 autosuspend（consumer.py）

Dream 执行时通过 `systemd-inhibit --what=sleep` 获取抑制剂锁，
autosuspend 调用的 `systemctl suspend` 会等待锁释放后才执行挂起。

```python
inhibitor = await asyncio.create_subprocess_exec(
    "systemd-inhibit", "--what=sleep", "--who=honcho-dream",
    "--why=Dream memory consolidation in progress",
    "--mode=block", "cat", ...
)
try:
    await process_dream(validated, workspace_name)
finally:
    inhibitor.terminate()
```

### 4. `TimeoutStartSec=120`（honcho-deriver.service）

deriver 启动超时由 systemd 强制 kill 并重试，防止 tiktoken 下载卡死。

## 部署

```bash
# 复制文件到 synbox
scp .env consumer.py dream_scheduler.py root@10.10.10.5:/tmp/

# 就位
ssh root@10.10.10.5 "
cp /tmp/.env /opt/honcho/.env
cp /tmp/consumer.py /opt/honcho/src/deriver/consumer.py
cp /tmp/dream_scheduler.py /opt/honcho/src/dreamer/dream_scheduler.py
systemctl restart honcho-deriver
"
```

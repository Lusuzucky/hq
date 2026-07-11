# NBFC + envycontrol GPU 模式动态切换

## 背景

Acer Aspire VN7-591G (V15 Nitro BE)，NVIDIA GTX 960M + Intel iGPU，使用 envycontrol 切换显卡模式，NBFC 控制双风扇散热。

**问题**：envycontrol 切换集显/混合模式后，NVIDIA 传感器 `nvidia-ml` 不可用，导致 NBFC 启动失败。envycontrol 每次切换都重建全部 initramfs（3 个镜像，381MB fallback），耗时 1-2 分钟。

## 解决方案

### 1. NBFC 动态配置

两套配置文件 + 预启动检测脚本，根据 GPU 实际状态自动选择。

```
/etc/nbfc/
  nbfc.json          -> nbfc.json.igpu (符号链接，自动切换)
  nbfc.json.igpu     不含 nvidia-ml 传感器
  nbfc.json.nvidia   含 nvidia-ml 传感器
```

- `/usr/local/bin/nbfc-pre-start` — 检测 `/dev/nvidia0` 是否存在，选择对应配置
- `/etc/systemd/system/nbfc_service.service.d/override.conf` — systemd drop-in，启动前执行检测脚本

### 2. mkinitcpio wrapper

envycontrol 只修改 rootfs 配置文件，不需要重建 initramfs。wrapper 检测到 envycontrol 调用时跳过重建。

```
/usr/bin/mkinitcpio       -> wrapper（检测父进程）
/usr/bin/mkinitcpio.real  -> 真正的 mkinitcpio
```

- 当父进程 cmdline 包含 `/envycontrol` 时，跳过并返回成功
- 其他调用（pacman hooks 等）正常透传到 `mkinitcpio.real`

## 安装

```bash
# NBFC 配置
sudo cp nbfc/nbfc.json.igpu /etc/nbfc/
sudo cp nbfc/nbfc.json.nvidia /etc/nbfc/
sudo cp nbfc/nbfc-pre-start /usr/local/bin/
sudo chmod 755 /usr/local/bin/nbfc-pre-start
sudo mkdir -p /etc/systemd/system/nbfc_service.service.d
sudo cp nbfc/override.conf /etc/systemd/system/nbfc_service.service.d/
sudo systemctl daemon-reload

# mkinitcpio wrapper
sudo mv /usr/bin/mkinitcpio /usr/bin/mkinitcpio.real
sudo cp mkinitcpio/wrapper /usr/bin/mkinitcpio
sudo chmod 755 /usr/bin/mkinitcpio
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `nbfc/nbfc.json.igpu` | 集显模式配置（coretemp/acpitz/ath10k_hwmon） |
| `nbfc/nbfc.json.nvidia` | 独显模式配置（额外包含 nvidia-ml） |
| `nbfc/nbfc-pre-start` | GPU 检测脚本，systemd ExecStartPre 调用 |
| `nbfc/override.conf` | systemd service drop-in |
| `mkinitcpio/wrapper` | 拦截 envycontrol 的 initramfs 重建 |

## 注意事项

- envycontrol 更新后会恢复 `/usr/bin/mkinitcpio`，需重新安装 wrapper
- NBFC 更新后配置文件可能变更，检查 `nbfc.json.*` 是否需要调整
- btrfs 快照使用 snapper，切换前建议 `sudo snapper create -d "描述" -c root`

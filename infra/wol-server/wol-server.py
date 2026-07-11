#!/usr/bin/env python3
"""
WOL Server — 运行在VPS上，usign Ed25519 挑战-应答认证

部署前先安装依赖和准备公钥:
  pip3 install pynacl
  将路由器的 /etc/wol.pub 复制到 VPS /etc/wol.pub

触发方式:
  echo "D8:43:AE:2D:92:3D" > /tmp/wol_trigger
"""

import socket
import threading
import time
import os
import sys
import secrets
import base64

try:
    from nacl.signing import VerifyKey
except ImportError:
    print("需要 pynacl: pip3 install pynacl", file=sys.stderr)
    sys.exit(1)

PORT     = int(os.environ.get("WOL_PORT", "19999"))
HEARTBEAT = int(os.environ.get("WOL_HEARTBEAT", "60"))
PUBKEY_FILE = os.environ.get("WOL_PUBKEY", "/etc/wol.pub")
TRIGGER_FILE = "/tmp/wol_trigger"

# 全局状态
wake_event = threading.Event()
wake_payload = ""
wake_lock = threading.Lock()

clients = []
clients_lock = threading.Lock()


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def load_pubkey_raw():
    """从 usign 公钥文件提取原始 32 字节 Ed25519 公钥
    usign 格式: base64(magic(2) + fingerprint(8) + pubkey(32)) → 42字节 → 取[10:]
    """
    with open(PUBKEY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("untrusted"):
                data = base64.b64decode(line)
                if len(data) == 32:
                    return data
                return data[10:]  # 去掉 magic(2) + fingerprint(8)
    raise ValueError(f"无法从 {PUBKEY_FILE} 解析公钥")


def usign_verify(msg: bytes, sig_b64: str, pubkey_raw: bytes) -> bool:
    """验证 usign 生成的 Ed25519 签名
    usign 签名格式: base64(magic(2) + fingerprint(8) + ed25519_sig(64)) → 74字节
    """
    try:
        raw = base64.b64decode(sig_b64)
        raw_sig = raw[10:]  # 去掉 magic(2) + fingerprint(8)
        if len(raw_sig) != 64:
            return False
        vk = VerifyKey(pubkey_raw)
        vk.verify(msg, raw_sig)
        return True
    except Exception:
        return False


def trigger_watcher():
    global wake_payload
    while True:
        try:
            with open(TRIGGER_FILE, "r") as f:
                content = f.read().strip()
            os.remove(TRIGGER_FILE)
            if content and content != "1":
                with wake_lock:
                    wake_payload = f"wake:{content}\n"
                wake_event.set()
                log(f"[!] 触发: wake:{content}")
        except FileNotFoundError:
            pass
        except Exception as e:
            log(f"[!] 读触发文件出错: {e}")
        time.sleep(1)


def handle(sock, addr):
    host, port = addr
    log(f"[*] {host}:{port} 新连接")

    # --- 握手认证 ---
    nonce = secrets.token_hex(16)
    try:
        sock.sendall(f"challenge:{nonce}\n".encode())
    except Exception as e:
        log(f"[-] {host} 发送挑战失败: {e}")
        sock.close()
        return

    try:
        sock.settimeout(10)
        resp = b""
        while b"\n" not in resp:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("对方关闭")
            resp += chunk
        line = resp.decode().strip()
    except Exception as e:
        log(f"[-] {host} 收认证响应失败: {e}")
        sock.close()
        return

    # 解析 auth:<nonce>:<sig_b64>
    parts = line.split(":", 2)
    if len(parts) != 3 or parts[0] != "auth" or parts[1] != nonce:
        log(f"[-] {host} 认证失败(格式错误): {line[:80]}")
        sock.close()
        return

    _, resp_nonce, sig_b64 = parts
    msg = f"wol-auth:{nonce}".encode()
    try:
        pubkey = load_pubkey_raw()
        if not usign_verify(msg, sig_b64, pubkey):
            log(f"[-] {host} 认证失败(签名无效)")
            sock.sendall(b"bad\n")
            sock.close()
            return
    except Exception as e:
        log(f"[-] {host} 验签异常: {e}")
        sock.sendall(b"bad\n")
        sock.close()
        return

    log(f"[+] {host}:{port} 认证通过")
    sock.sendall(b"ok\n")

    # --- 已认证：心跳 + 等待唤醒指令 ---
    with clients_lock:
        clients.append(sock)

    try:
        while True:
            triggered = wake_event.wait(HEARTBEAT)

            if triggered:
                wake_event.clear()
                with wake_lock:
                    payload = wake_payload.encode()
                log(f"[!] 向 {host} 发送: {payload.decode().strip()}")
                sock.sendall(payload)
            else:
                sock.sendall(b"\n")
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        log(f"[-] {host}:{port} 断开: {type(e).__name__}")
    finally:
        sock.close()
        with clients_lock:
            try:
                clients.remove(sock)
            except ValueError:
                pass
        log(f"[-] {host}:{port} 清理完毕")


def main():
    log(f"WOL Server 启动 :{PORT}  心跳:{HEARTBEAT}s  公钥:{PUBKEY_FILE}")

    threading.Thread(target=trigger_watcher, daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(10)

    while True:
        try:
            sock, addr = srv.accept()
            threading.Thread(target=handle, args=(sock, addr), daemon=True).start()
        except Exception as e:
            log(f"[*] accept 错误: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()

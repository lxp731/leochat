"""
Leochat CLI 配置管理
═══════════════════════════════════════════════════════════

配置优先级（高 → 低）：
  1. CLI 参数 (--server, --user)
  2. 环境变量 (LEOCHAT_SERVER, LEOCHAT_USER)
  3. ~/.config/leochat/config.toml
  4. 内置默认值

首次运行无配置文件时，交互式询问并持久化。
"""
import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Tuple


# ── 路径 ──────────────────────────────────────────────

def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg) / "leochat"


def config_path() -> Path:
    return _config_dir() / "config.toml"


# ── 默认值 ────────────────────────────────────────────

DEFAULTS: Dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 5000},
    "user": {"name": ""},
}


# ── 加载 / 保存 ───────────────────────────────────────

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """将 override 深度合并进 base（原地修改 base）"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load() -> Dict[str, Any]:
    """从 config.toml 加载配置，未设置的键回退到默认值"""
    config = deepcopy(DEFAULTS)
    cp = config_path()
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                data = tomllib.load(f)
            _deep_merge(config, data)
        except Exception:
            pass  # 文件损坏 → 回退默认值
    return config


def save(config: Dict[str, Any]) -> None:
    """将配置写回 config.toml"""
    cp = config_path()
    cp.parent.mkdir(parents=True, exist_ok=True)

    srv = config.get("server", {})
    usr = config.get("user", {})

    lines = [
        "# Leochat CLI 配置文件",
        "# 可以直接编辑，下次启动自动生效",
        "",
        "[user]",
        f'name = "{usr.get("name", "")}"',
        "",
        "[server]",
        f'host = "{srv.get("host", "127.0.0.1")}"',
        f"port = {srv.get('port', 5000)}",
        "",
    ]
    with open(cp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def is_first_run() -> bool:
    """配置文件不存在，或用户名为空 → 首次运行"""
    if not config_path().exists():
        return True
    config = load()
    return not config.get("user", {}).get("name", "")


# ── 配置解析（应用优先级链） ──────────────────────────

def parse_server_addr(raw: str) -> Tuple[str, int]:
    """解析 "host" 或 "host:port" 格式"""
    raw = raw.strip()
    if ":" in raw:
        # 处理 IPv6: [::1]:5000
        if raw.startswith("["):
            host, port_str = raw.rsplit(":", 1)
            host = host.strip("[]")
        else:
            host, port_str = raw.rsplit(":", 1)
        return host, int(port_str)
    return raw, 5000


def resolve() -> Dict[str, Any]:
    """加载配置并应用完整优先级链：配置文件 → 环境变量。
    
    CLI 参数的覆盖由调用方在 resolve() 之后自行处理。
    """
    config = load()

    # ── 环境变量覆盖 ──
    env_server = os.environ.get("LEOCHAT_SERVER", "")
    if env_server:
        host, port = parse_server_addr(env_server)
        config["server"]["host"] = host
        config["server"]["port"] = port

    env_user = os.environ.get("LEOCHAT_USER", "")
    if env_user:
        config["user"]["name"] = env_user

    return config


def server_url(config: Dict[str, Any]) -> str:
    """从配置 dict 构建完整的服务器 URL"""
    srv = config["server"]
    return f"http://{srv['host']}:{srv['port']}"

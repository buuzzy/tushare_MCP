import os
import sys
import traceback
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv, set_key
import tinyshare as ts
from .logger import log_debug

ENV_FILE = Path.home() / ".tinyshare_mcp" / ".env"
log_debug(f"ENV_FILE path resolved to: {ENV_FILE}")

def init_env_file():
    """初始化环境变量文件"""
    log_debug("init_env_file called.")
    try:
        log_debug(f"Attempting to create directory: {ENV_FILE.parent}")
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_debug(f"Directory {ENV_FILE.parent} ensured.")
        if not ENV_FILE.exists():
            log_debug(f"ENV_FILE {ENV_FILE} does not exist, attempting to touch.")
            ENV_FILE.touch()
            log_debug(f"ENV_FILE {ENV_FILE} touched.")
        else:
            log_debug(f"ENV_FILE {ENV_FILE} already exists.")
        load_dotenv(ENV_FILE)
        log_debug("load_dotenv(ENV_FILE) called.")
    except Exception as e_fs:
        log_debug(f"ERROR in init_env_file filesystem operations: {str(e_fs)}")
        traceback.print_exc(file=sys.stderr)

def get_tinyshare_token() -> Optional[str]:
    """获取Tinyshare token"""
    log_debug("get_tinyshare_token called.")
    init_env_file()
    token = os.getenv("TINYSHARE_TOKEN")
    log_debug(f"get_tinyshare_token: os.getenv result: {'TOKEN_FOUND' if token else 'NOT_FOUND'}")
    return token

def set_tinyshare_token(token: str):
    """设置Tinyshare token"""
    log_debug(f"set_tinyshare_token called with token: {'********' if token else 'None'}")
    init_env_file()
    try:
        set_key(ENV_FILE, "TINYSHARE_TOKEN", token)
        log_debug(f"set_key executed for ENV_FILE: {ENV_FILE}")
        ts.set_token(token)
        log_debug("ts.set_token(token) executed.")
    except Exception as e_set_token:
        log_debug(f"ERROR in set_tinyshare_token during set_key or ts.set_token: {str(e_set_token)}")
        traceback.print_exc(file=sys.stderr)

def get_pro_client():
    """Helper to get an authenticated tinyshare pro client"""
    token = get_tinyshare_token()
    if not token:
        raise ValueError("Tinyshare token not configured")
    return ts.pro_api(token)

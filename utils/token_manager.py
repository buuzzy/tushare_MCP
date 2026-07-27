import os
import sys
import traceback
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv, set_key
import tinyshare as ts  # minishare 数据 SDK（pip 包名仍为 tinyshare）
from .logger import log_debug

ENV_FILE = Path.home() / ".minishare_mcp" / ".env"
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

def get_data_token() -> Optional[str]:
    """获取数据授权码（行情/财报类）"""
    log_debug("get_data_token called.")
    init_env_file()
    token = os.getenv("TINYSHARE_TOKEN") or os.getenv("MINISHARE_DATA_TOKEN")
    log_debug(f"get_data_token: os.getenv result: {'TOKEN_FOUND' if token else 'NOT_FOUND'}")
    return token

def set_data_token(token: str):
    """设置数据授权码"""
    log_debug(f"set_data_token called with token: {'********' if token else 'None'}")
    init_env_file()
    try:
        set_key(ENV_FILE, "MINISHARE_DATA_TOKEN", token)
        log_debug(f"set_key executed for data token")
        ts.set_token(token)
        log_debug("data SDK set_token executed.")
    except Exception as e:
        log_debug(f"ERROR in set_data_token: {str(e)}")
        traceback.print_exc(file=sys.stderr)

def get_pro_client():
    """Helper to get an authenticated data pro client"""
    token = get_data_token()
    if not token:
        raise ValueError("Data token not configured")
    return ts.pro_api(token)


# ============================================================================
# Corpus token management (语料/资讯类接口)
# ============================================================================

def get_corpus_token() -> Optional[str]:
    """获取语料授权码（新闻/研报/公告类）"""
    log_debug("get_corpus_token called.")
    init_env_file()
    token = os.getenv("MINISHARE_TOKEN") or os.getenv("MINISHARE_CORPUS_TOKEN")
    log_debug(f"get_corpus_token: os.getenv result: {'TOKEN_FOUND' if token else 'NOT_FOUND'}")
    return token

def set_corpus_token(token: str):
    """设置语料授权码"""
    log_debug("set_corpus_token called.")
    init_env_file()
    try:
        set_key(ENV_FILE, "MINISHARE_CORPUS_TOKEN", token)
        log_debug("set_key executed for corpus token")
    except Exception as e:
        log_debug(f"ERROR in set_corpus_token: {str(e)}")
        traceback.print_exc(file=sys.stderr)

def get_corpus_client():
    """Helper to get an authenticated corpus pro client for news/research endpoints"""
    token = get_corpus_token()
    if not token:
        raise ValueError("Corpus token not configured")
    import minishare as ms
    return ms.pro_api(token)

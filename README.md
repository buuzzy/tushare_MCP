# Tushare MCP 📈

> 基于 MCP (Model Context Protocol) 协议构建的 A 股金融数据 AI 助手扩展 (v0.1.0)

<div align="center">

  <h3>让 AI 读懂中国股市</h3>
  <p>Claude Desktop / Cursor 无缝集成 · A 股/港股全量数据 · 财务报表 · 智能 Token 管理</p>

  <p>
    <img src="https://img.shields.io/badge/Protocol-MCP_1.0-blue?style=flat-square" alt="MCP">
    <img src="https://img.shields.io/badge/Language-Python_3.10+-3776ab?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/Framework-FastAPI-009688?style=flat-square" alt="FastAPI">
    <img src="https://img.shields.io/badge/Data-Tushare_Pro-orange?style=flat-square" alt="Tushare">
    <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" alt="License">
  </p>

  <p>
    <a href="#-核心功能">核心功能</a> •
    <a href="#-技术架构">技术架构</a> •
    <a href="#-快速开始">快速开始</a> •
    <a href="#-工具列表">工具列表</a> •
    <a href="#-项目结构">项目结构</a>
  </p>

</div>

---

**Tushare MCP** 是一款连接 AI（Claude, Cursor）与 Tushare 金融大数据的桥梁。它实现了 Model Context Protocol (MCP) 标准，让你的 AI 助手能够直接调用 30+ 个专业金融数据接口，实时查询股票行情、财务报表、公司基本面等关键数据。

## 🌟 核心功能

### 1. 🤖 完美适配主流 AI 客户端
*   **Claude Desktop**: 标准 SSE / Stdio 模式支持，本地直接运行。
*   **Cursor IDE**: 在编辑器中直接询问代码相关的股票数据，辅助金融编程。

### 2. 📊 全维度数据覆盖
*   **基础数据**: 股票列表、IPO 新股、交易日历、上市公司基本面。
*   **行情数据**: 日/周/月线行情、每日指标（PE/PB/市值）、涨跌停分析。
*   **财务报表**: 利润表、资产负债表、现金流量表、业绩预告、主营业务构成。
*   **特色数据**: 沪深港通十大成交股、融资融券、股权质押。

### 3. 🛠 智能 Token 管理
*   **一键配置**: 提供 `setup_tushare_token` 工具，对话即可完成配置。
*   **本地加密**: Token 安全存储于本地环境，无需重复输入。
*   **自动验证**: 启动时自动检查 Token 有效性。

### 4. ⚡ 高性能架构
*   **FastAPI 驱动**: 基于 FastAPI 构建的高性能 SSE 服务端。
*   **Tinyshare SDK**: 深度优化的 Tushare 接口封装，支持重试与异常处理。

## 🏗️ 技术架构

```mermaid
graph TD
    Client["AI Client (Claude / Cursor)"] -->|MCP Protocol (SSE / Stdio)| MCPServer[Tushare MCP Server]
    MCPServer -->|Tool Execution| Tools[Tool Implementation]
    Tools -->|Data Request| SDK[Tinyshare SDK]
    SDK -->|HTTP API| Tushare[("Tushare Pro API")]
    Tushare -->|JSON Data| SDK
    SDK -->|Structured Result| Tools
    Tools -->|Context| MCPServer
    MCPServer -->|Answer| Client
```

## 🚀 快速开始

### 1. 环境准备

确保已安装 python 3.10+。

```bash
# 1. 克隆项目
git clone <repository-url> tushare_mcp
cd tushare_mcp

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### 2. 配置说明

你也可以通过环境变量手动配置：

```bash
# 创建配置文件
touch .env

# 写入 Token（推荐使用 MCP 工具 setup_tushare_token 自动配置）
echo "TUSHARE_TOKEN=你的token" >> .env
```

### 3. 启动服务

#### 方式 A: HTTP Server (SSE 模式) - 推荐

适用于 Cursor 或此时同时也想查看 API 文档。

```bash
python server.py
# 服务将运行在 http://localhost:8000
# SSE 端点: http://localhost:8000/sse
```

#### 方式 B: Stdio 模式

适用于 Claude Desktop 本地集成。

```bash
python server.py --stdio
```

## 🔌 客户端连接

### Cursor 配置

1. 打开 Cursor Settings -> Features -> MCP
2. 点击 "+ Add New MCP Server"
3. 填写信息：
    *   **Name**: `tushare`
    *   **Type**: `SSE`
    *   **URL**: `http://localhost:8000/sse`

### Claude Desktop 配置

编辑配置文件 `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tushare": {
      "command": "/绝对路径/至/你的/venv/bin/python",
      "args": [
        "/绝对路径/至/你的/tushare_mcp/server.py",
        "--stdio"
      ]
    }
  }
}
```

## 🧰 工具列表

### 📈 基础与行情 (Stock)
| 工具名 | 说明 |
|:---|:---|
| `get_stock_basic` | 获取 A 股基础信息列表（代码、名称、上市日期等） |
| `get_trade_cal` | 获取各大交易所交易日历 |
| `get_stock_company` | 获取上市公司基本信息（注册资本、法人、简介） |
| `get_namechange` | 历史名称变更记录 |
| `get_stk_managers` | 上市公司管理层主要成员 |
| `get_daily` | A 股日线行情（开高低收、成交量）|
| `get_weekly` / `get_monthly` | 周线 / 月线行情 |
| `get_daily_basic` | 每日指标（换手率、量比、PE、PB、总市值） |
| `get_suspend_d` | 每日停复牌信息 |
| `get_hsgt_top10` | 沪深股通十大成交股 |

### 💰 财务数据 (Finance)
| 工具名 | 说明 |
|:---|:---|
| `get_income_statement` | 利润表 |
| `get_balance_sheet` | 资产负债表 |
| `get_cash_flow` | 现金流量表 |
| `get_forecast` | 业绩预告 |
| `get_express` | 业绩快报 |
| `get_fina_indicator` | 财务指标数据（EPS、ROE、毛利率等） |
| `get_fina_mainbz` | 主营业务构成 |
| `get_disclosure_date` | 财报披露计划日期 |

> 完整工具列表请查阅 `tools/` 目录或启动服务后访问 API 文档。

## 📁 项目结构

```
tushare_MCP/
├── api_docs/           # 原始 Tushare API 文档参考
├── mcp_test/           # MCP 工具测试记录
├── tools/              # MCP 工具实现核心代码
│   ├── finance/        # 财务类工具 (income, balance, cashflow...)
│   └── stock/
│       ├── basic/      # 基础数据工具 (stock_basic, trade_cal...)
│       └── quote/      # 行情数据工具 (daily, weekly, hsgt...)
├── utils/              # 通用工具函数 (logger, token_manager)
├── server.py           # MCP Server 入口 (FastAPI + FastMCP)
├── requirements.txt    # 项目依赖
└── README.md           # 项目文档
```

## 📄 License

MIT

---

<div align="center">
  <sub>Built with ❤️ using <a href="https://github.com/modelcontextprotocol" target="_blank">MCP</a> & <a href="https://tushare.pro/" target="_blank">Tushare Pro</a></sub>
</div>

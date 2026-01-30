# SmartRoute AI Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-cyan)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-green)](https://fastapi.tiangolo.com/)

一个现代化的、兼容 OpenAI 协议的智能路由网关。它能根据用户意图复杂度自动分流请求，支持多模型故障转移（Failover），并提供美观的 Web 管理面板。

![Dashboard Preview](docs/dashboard-preview.png)


## ✨ 核心特性

*   **⚡ 智能分流 (Intelligent Routing)**:
    *   **T1 (简单)**: 闲聊、短问答 -> 路由至低成本模型。
    *   **T2 (中等)**: 代码生成、文案写作 -> 路由至中等成本模型。
    *   **T3 (复杂)**: 深度推理、复杂逻辑 -> 路由至复杂成本模型。
    *   支持基于**关键词**的快速匹配或**LLM 意图识别**（使用小模型分析用户意图）。

*   **🛡️ 高可用与容错 (High Availability)**:
    *   **自动故障转移**: 当主模型返回 4xx/5xx 错误或超时，自动无缝切换到备用模型。
    *   **关键词重试**: 即使状态码为 200，若返回内容包含 "rate limit", "overloaded" 等关键词，也会自动重试。
    *   **参数自适应**: 支持为不同模型配置特定的默认参数（如 Kimi 强制 `top_p=0.95`），解决上游兼容性问题。

*   **📊 可视化管理面板**:
    *   **实时监控**: QPS、平均响应时间、错误率、模型使用分布。
    *   **日志审计**: 完整记录请求/响应体（JSON），支持流式响应重组记录。
    *   **在线配置**: 随时调整模型列表、超时时间、路由策略，无需重启服务。

*   **🔌 兼容性**:
    *   完全兼容 OpenAI `/v1/chat/completions` 协议。
    *   支持流式（Stream）与非流式响应。
    *   支持自定义网关鉴权（Gateway API Key）。

## 🔄 更新日志 (v1.1.0)

### ✨ 新增功能
*   **日志系统全面升级**:
    *   **持久化存储**: 现已完整记录请求错误堆栈 (Stack Trace) 和重试次数，确保系统故障可追溯。
    *   **移动端适配**: 优化了日志详情页面的侧边栏 UI，完美适配手机屏幕，解决了表格和堆栈信息溢出的问题。
    *   **高级筛选**: 重构了日志筛选栏 UI，采用现代化的日期选择器 (Calendar) 和下拉菜单 (Select)，支持按等级、状态、模型和时间范围精确查找。
    *   **数据导出**: 新增日志导出功能，支持将筛选结果一键下载为 CSV 报表。
*   **终端体验优化**:
    *   **CMD 风格**: 终端输出现在模仿 Windows CMD 风格，自动添加时间戳，并对 System/Success/Error/Warning 等关键词进行高亮着色。
    *   **信息完整性**: 终端能实时展示更详细的系统运行状态和错误提示。
*   **权限管理**:
    *   **安全加固**: 全面启用 Gateway API Key 鉴权，保护日志和配置接口不被未授权访问。
    *   **前端鉴权**: 优化了前端 401 处理流程，支持在界面上直接输入和保存 API Key。

### 🛠️ 修复与改进
*   **超时逻辑修复**: 修复了重试机制中连接超时判断不准确的问题，现在使用细粒度的 `connect`/`read` 超时配置，防止上游卡死导致重试阻塞。
*   **UI/UX 改进**: 统一了全站的输入控件风格，提升了整体视觉一致性。

---

## 🚀 快速启动

### Windows 用户 (推荐)

1.  确保已安装 [Python 3.10+](https://www.python.org/downloads/)。
2.  下载本项目源码。
3.  双击运行根目录下的 `start.bat`。
4.  脚本会自动创建虚拟环境、安装依赖并启动服务。
5.  浏览器访问 `http://localhost:6688` 进入管理面板。

### Linux / macOS / 手动部署

1.  **环境准备**:
    ```bash
    git clone https://github.com/yourusername/smart-route-ai-gateway.git
    cd smart-route-ai-gateway
    
    # 创建虚拟环境
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate   # Windows
    
    # 安装后端依赖
    pip install -r backend/requirements.txt
    ```

2.  **前端构建 (可选)**:
    *项目已包含预构建的前端文件。如需自行修改前端：*
    ```bash
    cd frontend
    npm install
    npm run build
    # 构建产物将生成在 frontend/dist
    ```

3.  **启动服务**:
    ```bash
    cd backend
    python main.py
    ```

## ⚙️ 配置说明

所有配置均可在 Web 面板 (`http://localhost:6688`) 中修改，也可以手动编辑 `backend/config.json`。

### 1. 路由策略
*   **T1/T2/T3 Models**: 定义不同复杂度级别对应的模型 ID 列表。
*   **Router Config**: 启用 `LLM 意图分析` 后，网关会先调用一个轻量模型（如 gpt-3.5）分析用户 prompt，再决定路由级别。
    *   **关闭时行为**: 如果关闭意图分析，系统将**不进行任何判断，直接在 T1/T2/T3 级别中随机选择一个**（Random Level Selection），实现简单的负载均衡。

### 2. 参数适配 (New)
为了兼容某些对参数有严格要求的国产大模型（如 Kimi, DeepSeek 等），支持在配置页面设置：
*   **全局参数 (Global Params)**: 对所有请求生效的默认值（如 `temperature: 0.7`）。
*   **特定模型参数 (Model Specific Params)**: 仅对特定模型生效，优先级最高。
    *   *示例*: 解决 Kimi 报错 `invalid top_p`
        ```json
        {
          "kimik2.5": { "top_p": 0.95 }
        }
        ```

### 3. 多供应商 (Multi-Provider) (New)
支持同时接入多个上游供应商（如 OpenAI, Azure, DeepSeek），并实现负载均衡或故障转移。

*   **供应商列表 (Providers)**: 定义多个供应商及其 URL/Key。
    ```json
    {
      "azure": { "base_url": "...", "api_key": "..." },
      "deepseek": { "base_url": "...", "api_key": "..." }
    }
    ```
*   **指定使用**: 在 T1/T2/T3 模型列表中，使用 `provider_id/model_name` 格式（如 `azure/gpt-4`）。
*   **自动映射 (Model Map)**: 将特定模型 ID 自动路由到指定供应商（如 `"gpt-4": "azure"`）。
*   **故障转移**: 配置 `t2_models: ["azure/gpt-4", "deepseek/deepseek-chat"]` 可实现当 Azure 失败时自动尝试 DeepSeek。

### 4. 上游配置 (默认)
*   **Upstream Base URL**: 默认的 LLM 供应商地址（用于未指定 Provider 的模型）。
*   **Upstream API Key**: 默认访问密钥。

### 5. 实时监控与日志 (New)
*   **实时终端**: 前端 `/terminal` 路由提供 WebSocket 实时日志流，支持暂停、过滤、导出。
*   **结构化日志**: 后端记录 5 个关键时间点（接收、调用、首包、完成），便于全链路性能分析。
*   **仪表盘优化**: 响应时间趋势图支持缩放与颜色分级（绿/黄/红）。

### 6. 版本升级与迁移
本项目采用向下兼容的配置管理机制。当软件版本更新引入新的配置项（如新增 `stream_timeouts`）时：
1.  **自动迁移**: 您无需手动修改现有的 `config.json` 文件。系统启动时会自动为缺失的字段填充默认值。
2.  **持久化**: 要将新字段永久保存到配置文件中，建议在升级后登录 Web 管理面板，点击右上角的 **"保存更改" (Save Changes)** 按钮即可。
3.  **无损更新**: 您的旧有配置（Key, URL, 模型列表等）会完全保留，不会被覆盖。

## 🛠️ 技术栈

*   **Backend**: Python, FastAPI, SQLAlchemy (Async), HTTPX
*   **Frontend**: React, Vite, Tailwind CSS, shadcn/ui
*   **Database**: SQLite (Async + WAL Mode)

## 🤝 贡献指南

欢迎提交 Issue 和 PR！

1.  Fork 本项目
2.  创建特性分支 (`git checkout -b feature/AmazingFeature`)
3.  提交更改 (`git commit -m 'Add some AmazingFeature'`)
4.  推送到分支 (`git push origin feature/AmazingFeature`)
5.  开启 Pull Request

## 📄 开源协议

MIT License

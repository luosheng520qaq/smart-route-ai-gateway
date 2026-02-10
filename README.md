# SmartRoute AI Gateway

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
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
    *   **智能健康检查**: 引入**时间衰减与动态惩罚机制**，模型错误分值会随时间自动恢复，偶发错误不会导致模型永久被 ban。
    *   **自动故障转移**: 当主模型返回 4xx/5xx 错误或超时，自动无缝切换到备用模型。
    *   **关键词重试**: 即使状态码为 200，若返回内容包含 "rate limit", "overloaded" 等关键词，也会自动重试。
    *   **参数自适应**: 支持为不同模型配置特定的默认参数（如 Kimi 强制 `top_p=0.95`），解决上游兼容性问题。

*   **🔒 企业级安全 (Enterprise Security)**:
    *   **JWT 认证**: 管理后台全站采用 JWT 令牌认证，支持会话管理。
    *   **2FA 双重验证**: 支持 Google Authenticator / TOTP 动态验证码，保护后台安全。
    *   **访问控制**: 细粒度的 Gateway API Key 控制，确保 API 调用安全。

*   **📊 可视化管理面板**:
    *   **实时监控**: QPS、平均响应时间、错误率、模型使用分布。
    *   **日志审计**: 完整记录请求/响应体（JSON），支持流式响应重组记录。
    *   **在线配置**: 随时调整模型列表、超时时间、路由策略，无需重启服务。

*   **🔌 兼容性**:
    *   完全兼容 OpenAI `/v1/chat/completions` 协议。
    *   支持流式（Stream）与非流式响应。
    *   支持自定义网关鉴权（Gateway API Key）。

## 🚀 快速开始

### 1. 快速安装

#### Windows
双击运行目录下的 `start.bat` 即可自动完成环境配置与启动。

#### Linux / macOS
我们提供了一键安装脚本，自动处理环境依赖、构建与启动。

推荐使用以下命令进行快速安装（只需一行）：

```bash
bash <(curl -sL https://raw.githubusercontent.com/luosheng520qaq/smart-route-ai-gateway/main/install.sh)
```

该命令会自动：
1. 检查并安装 Git (如果需要)。
2. 克隆项目代码。
3. 创建 Python 虚拟环境并安装依赖。
4. 自动生成启动脚本。

安装完成后，脚本会提示你如何启动服务。

### 2. 手动部署 (如果不使用脚本)

```bash
cd backend
# 创建虚拟环境
python -m venv venv
# 激活环境 (Windows)
venv\Scripts\activate
# 激活环境 (Linux/Mac)
source venv/bin/activate

# 安装依赖 (注意：包含安全组件)
pip install -r requirements.txt
```

### 3. 前端构建

```bash
cd frontend
npm install
npm run build
```
构建产物会自动生成到 `frontend/dist`，后端将自动托管。

### 4. 启动服务

```bash
cd backend
python main.py
```
服务默认运行在 `http://0.0.0.0:6688`。

## 🔐 默认账号与安全

系统采用**首次登录注册制**，没有预设密码。

1. **默认账号**: `admin`
2. **默认密码**: **首次登录时输入的任意密码**（系统会自动将其注册为永久密码）。
3. **强烈建议**: 首次登录后，请立即前往 **系统配置 -> 安全设置** 开启 **2FA 双重验证**。

## 📝 API 文档

*   **OpenAI 代理接口**: `POST /v1/chat/completions`
    *   认证: `Authorization: Bearer <Gateway-API-Key>` (如果在设置中配置了 Key)
*   **管理后台 API**: `/api/*`
    *   认证: `Authorization: Bearer <JWT-Token>` (通过登录获取)

## 🔄 旧版本升级指南

如果您是从旧版本升级：

1. **备份数据**: 备份 `backend/logs.db` 和 `backend/config.json` (可选)。
2. **更新代码**: 覆盖 `backend/` 和 `frontend/dist/`。
3. **更新依赖**: 务必运行 `pip install -r backend/requirements.txt` 以安装 `passlib`, `python-jose`, `pyotp` 等新依赖。
4. **重启服务**: 数据库会自动迁移，添加用户表。

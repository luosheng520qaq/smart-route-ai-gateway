#!/bin/bash
cd "$(dirname "$0")"

# 颜色
GREEN='\033[0;32m'
NC='\033[0m'

# 检查 venv
if [ ! -d "venv" ]; then
    echo "未找到虚拟环境，正在尝试运行安装脚本..."
    if [ -f "install.sh" ]; then
        chmod +x install.sh
        ./install.sh
        if [ $? -ne 0 ]; then
            exit 1
        fi
    else
        echo "错误: 未找到 venv 且未找到 install.sh。请确保已正确安装。"
        exit 1
    fi
fi

# 激活环境
source venv/bin/activate

echo -e "${GREEN}SmartRoute AI Gateway 启动中...${NC}"
echo -e "${GREEN}管理面板: http://localhost:6688${NC}"
echo -e "${GREEN}API 地址: http://localhost:6688/v1${NC}"

cd backend
python main.py

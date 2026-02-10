#!/bin/bash

# ==========================================
# Smart Route AI Gateway Linux 一键安装脚本
# ==========================================

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   Smart Route AI Gateway 安装向导        ${NC}"
echo -e "${GREEN}==========================================${NC}"

# 1. 环境检查
echo -e "${YELLOW}[1/4] 正在检查系统环境...${NC}"

# 检查 git
if ! command -v git &> /dev/null; then
    echo -e "${RED}错误: 未找到 git。正在尝试自动安装...${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    else
        echo -e "${RED}无法自动安装 git，请手动安装后重试。${NC}"
        exit 1
    fi
fi

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3。${NC}"
    echo "请安装 Python 3.10 或更高版本："
    echo "Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "CentOS/RHEL: sudo yum install -y python3"
    exit 1
fi

# 2. 代码拉取与目录处理
echo -e "${YELLOW}[2/4] 准备项目代码...${NC}"

# 判断是否在项目根目录下运行 (通过检查 backend/main.py 是否存在)
if [ -f "backend/main.py" ]; then
    echo -e "${GREEN}检测到当前已在项目目录中，直接进行配置。${NC}"
else
    # 不在项目目录，需要克隆或进入
    REPO_URL="https://github.com/luosheng520qaq/smart-route-ai-gateway.git"
    DIR_NAME="smart-route-ai-gateway"

    if [ -d "$DIR_NAME" ]; then
        echo -e "${YELLOW}检测到目录 $DIR_NAME 已存在，正在更新...${NC}"
        cd "$DIR_NAME"
        git pull
    else
        echo -e "${YELLOW}正在克隆仓库...${NC}"
        git clone "$REPO_URL"
        if [ $? -ne 0 ]; then
            echo -e "${RED}克隆失败，请检查网络连接。${NC}"
            exit 1
        fi
        cd "$DIR_NAME"
    fi
fi

# 3. 后端环境配置
echo -e "${YELLOW}[3/4] 配置 Python 后端环境...${NC}"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境 (venv)..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}虚拟环境创建失败！请尝试安装 python3-venv 包：${NC}"
        echo "Ubuntu/Debian: sudo apt install python3-venv"
        exit 1
    fi
fi

# 激活并安装依赖
echo "安装/更新 Python 依赖..."
source venv/bin/activate
pip install --upgrade pip
# 使用清华源加速
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if [ $? -ne 0 ]; then
    echo -e "${RED}依赖安装失败！请检查网络或错误信息。${NC}"
    exit 1
fi

# 检查前端文件 (仅提示)
if [ ! -d "frontend/dist" ]; then
    echo -e "${RED}警告: 未检测到 frontend/dist 目录。${NC}"
    echo -e "${YELLOW}如果是直接克隆仓库，请确保仓库中包含 dist 目录，或者手动上传前端构建文件。${NC}"
else
    echo -e "${GREEN}检测到前端文件，准备就绪。${NC}"
fi

# 4. 生成启动脚本
echo -e "${YELLOW}[4/4] 完成安装配置...${NC}"

# 创建 start.sh 如果不存在
if [ ! -f "start.sh" ]; then
    echo "生成 start.sh..."
    cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

# 颜色
GREEN='\033[0;32m'
NC='\033[0m'

# 检查 venv
if [ ! -d "venv" ]; then
    echo "未找到虚拟环境，请先运行 install.sh"
    exit 1
fi

# 激活环境
source venv/bin/activate

echo -e "${GREEN}SmartRoute AI Gateway 启动中...${NC}"
echo -e "${GREEN}管理面板: http://localhost:6688${NC}"
echo -e "${GREEN}API 地址: http://localhost:6688/v1${NC}"

cd backend
python main.py
EOF
fi

chmod +x start.sh

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   安装全部完成！                         ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e "当前目录: $(pwd)"
echo -e "启动命令: ${YELLOW}./start.sh${NC}"
echo -e "后台运行推荐: ${YELLOW}nohup ./start.sh > run.log 2>&1 &${NC}"

#!/bin/bash
# 知识库查看器启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📚 知识库本地查看器${NC}"
echo

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 未找到 Node.js${NC}"
    echo "请安装 Node.js (版本 14 或更高)"
    exit 1
fi

# 默认值
NOTES_DIR="./notes"
PORT="3000"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            NOTES_DIR="$2"
            shift 2
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [选项]"
            echo "选项:"
            echo "  -d, --dir DIR   指定知识库目录 (默认: ./notes)"
            echo "  -p, --port PORT 指定端口 (默认: 3000)"
            echo "  -h, --help      显示此帮助信息"
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            echo "使用 $0 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 检查目录是否存在，不存在则创建
if [ ! -d "$NOTES_DIR" ]; then
    echo -e "${YELLOW}⚠️  目录不存在，创建: $NOTES_DIR${NC}"
    mkdir -p "$NOTES_DIR"
fi

# 检查端口是否被占用
if command -v lsof &> /dev/null; then
    if lsof -i:$PORT &> /dev/null; then
        echo -e "${YELLOW}⚠️  端口 $PORT 已被占用，尝试使用其他端口${NC}"
        # 查找可用端口
        for ((p=PORT+1; p<=PORT+10; p++)); do
            if ! lsof -i:$p &> /dev/null; then
                PORT=$p
                echo -e "${GREEN}✅ 使用端口: $PORT${NC}"
                break
            fi
        done
    fi
fi

echo -e "${GREEN}✅ Node.js 版本:$(node -v)${NC}"
echo -e "${GREEN}✅ 知识库目录:$(realpath "$NOTES_DIR")${NC}"
echo -e "${GREEN}✅ 端口: $PORT${NC}"
echo

# 启动服务器
echo -e "${BLUE}🚀 启动服务器...${NC}"
echo

node server.js "$NOTES_DIR" "$PORT" &
SERVER_PID=$!

# 等待服务器启动
sleep 2

# 检查服务器是否运行
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}✅ 服务器已启动 (PID: $SERVER_PID)${NC}"
    echo
    echo -e "${BLUE}📖 访问地址:${NC}"
    echo -e "  本地: ${GREEN}http://localhost:$PORT${NC}"

    # 获取本地IP地址
    if command -v ip &> /dev/null; then
        IP=$(ip route get 1 | awk '{print $NF;exit}')
    elif command -v ifconfig &> /dev/null; then
        IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -n1)
    fi

    if [ -n "$IP" ]; then
        echo -e "  网络: ${GREEN}http://$IP:$PORT${NC}"
    fi

    echo
    echo -e "${YELLOW}📌 按 Ctrl+C 停止服务器${NC}"

    # 尝试打开浏览器
    if command -v xdg-open &> /dev/null; then
        xdg-open "http://localhost:$PORT" > /dev/null 2>&1 &
    elif command -v open &> /dev/null; then
        open "http://localhost:$PORT" > /dev/null 2>&1 &
    fi

    # 等待服务器进程
    wait $SERVER_PID
else
    echo -e "${RED}❌ 服务器启动失败${NC}"
    exit 1
fi
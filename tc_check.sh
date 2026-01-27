#!/bin/bash
# TC 限速配置检查和诊断工具
# 用于验证 TC 限速功能是否正常工作

set -e

TC_USERS_CONF="/etc/openvpn/tc-users.conf"
TC_ROLES_MAP="/etc/openvpn/tc-roles.map"
STATUS_LOG="/var/log/openvpn/status.log"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "==================================================================="
echo "===       TC 流量控制限速功能诊断工具                        ==="
echo "==================================================================="
echo ""

# 1. 检查必需的系统工具
echo -e "${BLUE}[1/10]${NC} 检查必需的系统工具..."
REQUIRED_TOOLS=("tc" "ip" "modprobe" "awk" "lsmod")
ALL_TOOLS_PRESENT=true

for tool in "${REQUIRED_TOOLS[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${RED}✗${NC} $tool - 缺失！"
        ALL_TOOLS_PRESENT=false
    fi
done

if [ "$ALL_TOOLS_PRESENT" = false ]; then
    echo -e "${RED}错误: 缺少必需的系统工具！${NC}"
    echo "请运行: sudo apt install iproute2 kmod"
    exit 1
fi

# 2. 检查 ifb 内核模块
echo ""
echo -e "${BLUE}[2/10]${NC} 检查 ifb 内核模块..."
if lsmod | grep -q "^ifb\b"; then
    echo -e "  ${GREEN}✓${NC} ifb 模块已加载"
    
    # 检查 ifb0 设备
    if ip link show ifb0 >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} ifb0 设备存在"
        
        # 检查 ifb0 是否 UP
        if ip link show ifb0 | grep -q "UP"; then
            echo -e "  ${GREEN}✓${NC} ifb0 设备已启动"
        else
            echo -e "  ${YELLOW}⚠${NC}  ifb0 设备未启动"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC}  ifb0 设备不存在"
    fi
else
    echo -e "  ${RED}✗${NC} ifb 模块未加载"
    echo "  尝试加载: sudo modprobe ifb"
fi

# 3. 检查 OpenVPN 服务状态
echo ""
echo -e "${BLUE}[3/10]${NC} 检查 OpenVPN 服务..."
if systemctl is-active --quiet openvpn@server.service; then
    echo -e "  ${GREEN}✓${NC} OpenVPN 服务运行中"
    
    # 检查 tun0 设备
    if ip link show tun0 >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} tun0 设备存在"
    else
        echo -e "  ${RED}✗${NC} tun0 设备不存在"
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  OpenVPN 服务未运行"
    echo "  TC 限速服务依赖 OpenVPN，请先启动 OpenVPN"
fi

# 4. 检查 TC 守护进程服务
echo ""
echo -e "${BLUE}[4/10]${NC} 检查 TC 守护进程服务..."
if systemctl is-active --quiet vpn-tc-daemon.service; then
    echo -e "  ${GREEN}✓${NC} vpn-tc-daemon 服务运行中"
    
    # 显示最近日志
    echo "  最近日志:"
    sudo journalctl -u vpn-tc-daemon.service -n 5 --no-pager 2>/dev/null | sed 's/^/    /'
else
    echo -e "  ${RED}✗${NC} vpn-tc-daemon 服务未运行"
    
    # 检查服务是否启用
    if systemctl is-enabled --quiet vpn-tc-daemon.service 2>/dev/null; then
        echo -e "  ${YELLOW}⚠${NC}  服务已启用但未运行，查看错误日志:"
        sudo journalctl -u vpn-tc-daemon.service -n 10 --no-pager 2>/dev/null | sed 's/^/    /'
    else
        echo -e "  ${YELLOW}⚠${NC}  服务未启用"
    fi
fi

# 5. 检查 TC 配置文件
echo ""
echo -e "${BLUE}[5/10]${NC} 检查 TC 配置文件..."

if [ -f "$TC_USERS_CONF" ]; then
    echo -e "  ${GREEN}✓${NC} $TC_USERS_CONF 存在"
    
    # 检查文件内容
    CONF_LINES=$(grep -v "^#" "$TC_USERS_CONF" | grep -v "^$" | wc -l)
    echo "    配置行数: $CONF_LINES"
    
    if [ $CONF_LINES -gt 0 ]; then
        echo "    配置内容预览:"
        grep -v "^#" "$TC_USERS_CONF" | grep -v "^$" | head -5 | sed 's/^/      /'
    else
        echo -e "    ${YELLOW}⚠${NC}  配置文件为空"
    fi
else
    echo -e "  ${RED}✗${NC} $TC_USERS_CONF 不存在"
fi

if [ -f "$TC_ROLES_MAP" ]; then
    echo -e "  ${GREEN}✓${NC} $TC_ROLES_MAP 存在"
    
    # 检查文件内容
    MAP_LINES=$(grep -v "^#" "$TC_ROLES_MAP" | grep -v "^$" | wc -l)
    echo "    映射行数: $MAP_LINES"
    
    if [ $MAP_LINES -gt 0 ]; then
        echo "    映射内容预览:"
        grep -v "^#" "$TC_ROLES_MAP" | grep -v "^$" | head -5 | sed 's/^/      /'
    else
        echo -e "    ${YELLOW}⚠${NC}  映射文件为空"
    fi
else
    echo -e "  ${RED}✗${NC} $TC_ROLES_MAP 不存在"
fi

# 6. 检查 OpenVPN 状态文件
echo ""
echo -e "${BLUE}[6/10]${NC} 检查 OpenVPN 状态文件..."
if [ -f "$STATUS_LOG" ]; then
    echo -e "  ${GREEN}✓${NC} $STATUS_LOG 存在"
    
    # 检查文件最后修改时间
    LAST_MODIFIED=$(stat -c %y "$STATUS_LOG" 2>/dev/null | cut -d'.' -f1)
    echo "    最后更新: $LAST_MODIFIED"
    
    # 检查在线客户端数量
    ONLINE_COUNT=$(awk -F, '/^ROUTING TABLE/,/^GLOBAL STATS/ {if($1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) print $1}' "$STATUS_LOG" 2>/dev/null | wc -l)
    echo "    在线客户端: $ONLINE_COUNT"
    
    if [ $ONLINE_COUNT -gt 0 ]; then
        echo "    在线客户端列表:"
        awk -F, '/^ROUTING TABLE/,/^GLOBAL STATS/ {if($1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) print "      " $2 " (" $1 ")"}' "$STATUS_LOG" 2>/dev/null | head -10
    fi
else
    echo -e "  ${RED}✗${NC} $STATUS_LOG 不存在"
    echo "    OpenVPN 可能未配置状态日志"
fi

# 7. 检查 tun0 的 TC 规则
echo ""
echo -e "${BLUE}[7/10]${NC} 检查 tun0 的 TC 规则..."
if ip link show tun0 >/dev/null 2>&1; then
    # 检查 root qdisc
    if tc qdisc show dev tun0 2>/dev/null | grep -q "htb 1:"; then
        echo -e "  ${GREEN}✓${NC} tun0 root qdisc 已配置 (htb 1:)"
    else
        echo -e "  ${RED}✗${NC} tun0 root qdisc 未配置"
        echo "    当前配置:"
        tc qdisc show dev tun0 2>/dev/null | sed 's/^/      /'
    fi
    
    # 检查 class 数量
    CLASS_COUNT=$(tc class show dev tun0 2>/dev/null | grep "class htb 1:" | wc -l)
    echo "    HTB class 数量: $CLASS_COUNT"
    
    if [ $CLASS_COUNT -gt 0 ]; then
        echo "    前 5 个 class:"
        tc class show dev tun0 2>/dev/null | grep "class htb 1:" | head -5 | sed 's/^/      /'
    fi
    
    # 检查 filter 数量
    FILTER_COUNT=$(tc filter show dev tun0 2>/dev/null | grep "filter" | wc -l)
    echo "    filter 数量: $FILTER_COUNT"
    
    # 检查 ingress
    if tc qdisc show dev tun0 2>/dev/null | grep -q "ingress"; then
        echo -e "  ${GREEN}✓${NC} tun0 ingress qdisc 已配置"
    else
        echo -e "  ${YELLOW}⚠${NC}  tun0 ingress qdisc 未配置"
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  tun0 设备不存在"
fi

# 8. 检查 ifb0 的 TC 规则
echo ""
echo -e "${BLUE}[8/10]${NC} 检查 ifb0 的 TC 规则..."
if ip link show ifb0 >/dev/null 2>&1; then
    # 检查 root qdisc
    if tc qdisc show dev ifb0 2>/dev/null | grep -q "htb 2:"; then
        echo -e "  ${GREEN}✓${NC} ifb0 root qdisc 已配置 (htb 2:)"
    else
        echo -e "  ${RED}✗${NC} ifb0 root qdisc 未配置"
        echo "    当前配置:"
        tc qdisc show dev ifb0 2>/dev/null | sed 's/^/      /'
    fi
    
    # 检查 class 数量
    CLASS_COUNT=$(tc class show dev ifb0 2>/dev/null | grep "class htb 2:" | wc -l)
    echo "    HTB class 数量: $CLASS_COUNT"
    
    if [ $CLASS_COUNT -gt 0 ]; then
        echo "    前 5 个 class:"
        tc class show dev ifb0 2>/dev/null | grep "class htb 2:" | head -5 | sed 's/^/      /'
    fi
    
    # 检查 filter 数量
    FILTER_COUNT=$(tc filter show dev ifb0 2>/dev/null | grep "filter" | wc -l)
    echo "    filter 数量: $FILTER_COUNT"
else
    echo -e "  ${YELLOW}⚠${NC}  ifb0 设备不存在"
fi

# 9. 检查 iptables/nftables 冲突
echo ""
echo -e "${BLUE}[9/10]${NC} 检查防火墙配置..."

# 检查 iptables
if command -v iptables >/dev/null 2>&1; then
    IPTABLES_RULES=$(sudo iptables -t mangle -L -n 2>/dev/null | grep -c "tun0" || echo "0")
    if [ "$IPTABLES_RULES" -gt 0 ]; then
        echo -e "  ${YELLOW}ℹ${NC}  检测到 iptables mangle 规则涉及 tun0"
        echo "    这可能影响 TC 行为，但通常不会冲突"
    else
        echo -e "  ${GREEN}✓${NC} iptables 未检测到与 TC 的潜在冲突"
    fi
fi

# 检查 nftables
if command -v nft >/dev/null 2>&1; then
    if nft list ruleset 2>/dev/null | grep -q "tun0"; then
        echo -e "  ${YELLOW}ℹ${NC}  检测到 nftables 规则涉及 tun0"
        echo "    这可能影响 TC 行为，但通常不会冲突"
    else
        echo -e "  ${GREEN}✓${NC} nftables 未检测到与 TC 的潜在冲突"
    fi
fi

# 10. 综合诊断
echo ""
echo -e "${BLUE}[10/10]${NC} 综合诊断..."

ISSUES=()
WARNINGS=()

# 检查关键问题
if ! lsmod | grep -q "^ifb\b"; then
    ISSUES+=("ifb 模块未加载")
fi

if ! systemctl is-active --quiet openvpn@server.service; then
    WARNINGS+=("OpenVPN 服务未运行")
fi

if ! systemctl is-active --quiet vpn-tc-daemon.service; then
    ISSUES+=("TC 守护进程未运行")
fi

if ! ip link show tun0 >/dev/null 2>&1; then
    ISSUES+=("tun0 设备不存在")
fi

if ! ip link show ifb0 >/dev/null 2>&1; then
    ISSUES+=("ifb0 设备不存在")
fi

if ! tc qdisc show dev tun0 2>/dev/null | grep -q "htb 1:"; then
    ISSUES+=("tun0 TC 规则未配置")
fi

if ! tc qdisc show dev ifb0 2>/dev/null | grep -q "htb 2:"; then
    ISSUES+=("ifb0 TC 规则未配置")
fi

if [ ! -f "$TC_USERS_CONF" ]; then
    ISSUES+=("TC 用户配置文件不存在")
fi

if [ ! -f "$STATUS_LOG" ]; then
    WARNINGS+=("OpenVPN 状态文件不存在")
fi

# 输出诊断结果
echo ""
if [ ${#ISSUES[@]} -eq 0 ] && [ ${#WARNINGS[@]} -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ 所有检查通过，TC 限速功能正常！${NC}"
    echo -e "${GREEN}========================================${NC}"
elif [ ${#ISSUES[@]} -eq 0 ]; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}⚠ 发现警告，但不影响核心功能${NC}"
    echo -e "${YELLOW}========================================${NC}"
    for warning in "${WARNINGS[@]}"; do
        echo -e "  ${YELLOW}⚠${NC} $warning"
    done
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ 发现问题，TC 限速功能可能异常${NC}"
    echo -e "${RED}========================================${NC}"
    for issue in "${ISSUES[@]}"; do
        echo -e "  ${RED}✗${NC} $issue"
    done
    
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        echo ""
        echo "警告:"
        for warning in "${WARNINGS[@]}"; do
            echo -e "  ${YELLOW}⚠${NC} $warning"
        done
    fi
fi

echo ""
echo "==================================================================="
echo "诊断完成！"
echo ""
echo "常用修复命令:"
echo "  加载 ifb 模块:      sudo modprobe ifb"
echo "  启动 TC 服务:       sudo systemctl start vpn-tc-daemon.service"
echo "  重启 TC 服务:       sudo systemctl restart vpn-tc-daemon.service"
echo "  查看 TC 日志:       sudo journalctl -u vpn-tc-daemon.service -f"
echo "  清理 TC 规则:       sudo tc qdisc del dev tun0 root 2>/dev/null"
echo "                     sudo tc qdisc del dev tun0 ingress 2>/dev/null"
echo "                     sudo tc qdisc del dev ifb0 root 2>/dev/null"
echo "==================================================================="
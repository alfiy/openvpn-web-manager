# Opnevpn web配置管理页面



## 运行项目

目前项目仅支持ubuntu操作系统，开发及测试环境为ubuntu 2204 server

0. 安装依赖
sudo apt install python3.12-venv

1. 进入项目目录执行下面的命令
第一次运行时执行下面的命令进行openvpn-web-manager项目的安装。
sudo ./run.sh
安装成功后使用`systemctl`管理vpnwm服务

```bash
# 启动vpnwm
sudo systemctl start vpnwm
# 停止vpnwm
sudo systemctl stop vpnwm
# 重启
sudo systemctl restart vpnwm
# 查看
sudo systemctl status vpnwm
```

2. 通过web界面管理vpn客户端

http://your-ip-address:8080




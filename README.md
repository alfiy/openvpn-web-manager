# Opnevpn web配置管理页面



## 运行项目

目前项目仅支持ubuntu操作系统，开发环境为ubuntu 2204 desktop，测试环境为ubuntu2204 server。

0. 安装依赖
```bash
# ubuntu 2404
sudo apt install python3.12-venv
# ubuntu 2204
sudo apt install python3.10-venv
```

配置邮件服务
修改`.env`配置文件，根据实际情况填写

```bash
MAIL_SERVER=smtp.qq.com
MAIL_PORT=465
MAIL_USE_SSL=true
MAIL_USE_TLS=false
MAIL_USERNAME=888888@qq.com
MAIL_PASSWORD=16位授权码
MAIL_DEFAULT_SENDER=888888@qq.com
```


1. 项目部署

使用下面的部署脚本进行部署

```bash
./deploy.sh

# 部署成功后，使用下面的命令启动
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
```bash
http://your-ip-address:8080
```

3. 登录系统

系统安装时默认添加了两个用户，super_admin和admin,密码均为admin123.

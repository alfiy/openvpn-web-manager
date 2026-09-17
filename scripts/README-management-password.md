# OpenVPN management 口密码

7505 只应绑在 127.0.0.1。加上口令后，本机其它进程也不能随便 `status` / `kill`。

Web 代码从环境变量读取：

```text
OPENVPN_MGMT_HOST=127.0.0.1
OPENVPN_MGMT_PORT=7505
OPENVPN_MGMT_PASSWORD=这里填与文件相同的密码
```

未设置 `OPENVPN_MGMT_PASSWORD` 时，行为与现在相同（无密码也能连）。

## 生产启用（会重启 OpenVPN）

```bash
sudo install -m 600 -o root -g root /dev/null /etc/openvpn/mgmt.pass
# 文件里只写一行密码，不要换行空格
echo '请改成足够长的随机串' | sudo tee /etc/openvpn/mgmt.pass >/dev/null
sudo chmod 600 /etc/openvpn/mgmt.pass
```

`/etc/openvpn/server.conf` 在现有 `management` 下增加：

```text
management 127.0.0.1 7505
management-client-pass /etc/openvpn/mgmt.pass
```

不要打开 `management-client-auth`（那是证书客户端认证，不是管理口密码）。

把同一密码写入 `/opt/vpnwm/.env`（不要提交到 git）：

```text
OPENVPN_MGMT_PASSWORD=请改成足够长的随机串
```

```bash
sudo chmod 600 /opt/vpnwm/.env
sudo systemctl restart openvpn@server
sudo systemctl restart vpnwm
```

验证：

```bash
# 无密码应被拒绝或停在 PASSWORD
python3 - << 'PY'
import os, socket
s = socket.create_connection(('127.0.0.1', 7505), 3)
s.settimeout(2)
print(s.recv(4096))
s.close()
PY
```

看到要密码后，页面在线列表、踢人应仍可用。first-wins 不访问 7505，不受影响。
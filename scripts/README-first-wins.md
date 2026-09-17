# 同一证书「先连的赢」部署说明

脚本：`scripts/openvpn-first-wins.sh`（当前日志标记 **HOOK start v4**）

目标：同一张客户端证书，先连上的会话保持在线；后连的被拒绝。后连的官方客户端会自动重试，但不得把先连的踢掉。先连的断开后，锁释放，任意一端可以再连。

测试机已用 `test-505`、v4 脚本验证通过。

---

## 正确行为（v4）

| 步骤                               | 日志                                         |
| ---------------------------------- | -------------------------------------------- |
| A 连上                             | `HOOK start v4` + `ALLOW take-lock`          |
| B 用同一证书再连                   | `DENY holder=A的IP:端口 age=Ns (lock-fresh)` |
| B 被拒后 OpenVPN 仍会走 disconnect | `UNLOCK skip rejected-or-other holder=A...`  |
| A 保持在线                         | status 里该 CN 只有一条                      |
| A 主动断开                         | `UNLOCK released holder=A...`                |
| 之后 A 或 B 再连                   | `ALLOW take-lock`                            |

---

## 生产部署

选可以短暂中断全部 VPN 的窗口（改 `server.conf` 后必须重启 OpenVPN）。

### 1. 安装脚本和可写目录

OpenVPN 使用 `user nobody`，hook **以 nobody 运行**。systemd 常见 `ReadWritePaths=/etc/openvpn` 和 `PrivateTmp=true`。

因此：

- 不要把日志写到 `/tmp`（主机上看不见，或 nobody 写不了你以为的那个 `/tmp`）
- 不要把日志写到 `/var/log/openvpn/first-wins.log`（root:644 时 nobody 写不进去，表现为「日志一直空」）
- 必须先用 root 建好 `/etc/openvpn/first-wins`

```bash
sudo mkdir -p /etc/openvpn/scripts
sudo mkdir -p /etc/openvpn/first-wins/locks
sudo chown -R nobody:nogroup /etc/openvpn/first-wins
sudo chmod 755 /etc/openvpn/first-wins
sudo chmod 1777 /etc/openvpn/first-wins/locks

sudo cp /opt/vpnwm/scripts/openvpn-first-wins.sh /etc/openvpn/scripts/openvpn-first-wins.sh
# 若该路径没有脚本，改用项目目录：
# sudo cp scripts/openvpn-first-wins.sh /etc/openvpn/scripts/openvpn-first-wins.sh
sudo chmod 755 /etc/openvpn/scripts/openvpn-first-wins.sh
sudo chown root:root /etc/openvpn/scripts/openvpn-first-wins.sh

grep -n "HOOK start v4" /etc/openvpn/scripts/openvpn-first-wins.sh
```

最后一条应能搜到 `v4`，否则拷错了文件。

### 2. 修改 /etc/openvpn/server.conf

以下行必须生效（行首不能有 `#`），其它原有配置不要动：

```text
user nobody
group nogroup
duplicate-cn
script-security 2
client-connect /etc/openvpn/scripts/openvpn-first-wins.sh
client-disconnect /etc/openvpn/scripts/openvpn-first-wins.sh
management 127.0.0.1 7505
```

- **必须开 `duplicate-cn`**：不开时服务端会先拆掉旧连接，脚本还没判断人就已经被顶掉。
- **必须同时配 `client-disconnect`**：先连的正常下线后才能释放锁。
- `management` 给网页踢人/在线列表用，本脚本 **不要在 hook 里访问 7505**（会和正在处理连接的 OpenVPN 死锁）。
- 不要打开 `management-client-auth`。

### 3. 重启 OpenVPN

```bash
sudo systemctl restart openvpn@server
sudo systemctl is-active openvpn@server
ss -lntp | grep 7505
```

现网隧道会全部断开一次，客户端会重连，先连上的占锁。

### 4. 验收

```bash
sudo tail -f /etc/openvpn/first-wins/first-wins.log
ls -l /etc/openvpn/first-wins/locks
sudo grep test-505 /var/log/openvpn/status.log
```

先只开客户端 A，再开 B（同一证书）。B 的日志必须是 `DENY` + `UNLOCK skip`，不能是 `ALLOW take-lock`。  
关掉 A 后应出现 `UNLOCK released`，此时再连 A 或 B 才能成功。

---

## 测试过程中踩过的坑

### 1. 没开 `duplicate-cn`

现象：先连的被顶掉，后连的上来，两边互踢；`first-wins.log` 没有 `DENY`。

原因：OpenVPN 默认后来者替换先来者，hook 跑的时候旧会话已经没了。

处理：`server.conf` 里打开 `duplicate-cn`。

### 2. 日志一直空，以为脚本没跑

常见有三种，不要只盯着一个路径：

| 路径                                            | 问题                                                         |
| ----------------------------------------------- | ------------------------------------------------------------ |
| `/var/log/openvpn/first-wins.log`               | nobody 写不了 root 的 644 文件                               |
| `/tmp/openvpn-first-wins.log`                   | systemd `PrivateTmp` 下写的是服务私有 /tmp，主机 `ls /tmp` 看不到 |
| 只重启了 `openvpn@server`、还没让客户端真正握手 | hook 只在客户端连接/断开时执行，重启服务不会建日志           |

正确日志：`/etc/openvpn/first-wins/first-wins.log`  
目录必须事先由 root 创建并 `chown nobody:nogroup`。

### 3. 在 client-connect 里查 7505

现象：两个客户端都能拿到不同虚拟 IP（如 10.8.0.2 和 10.8.0.3）并一直在线。

原因：hook 执行时 OpenVPN 正忙着处理这条连接，再连本机 management 容易超时/空结果，脚本误判「没人在线」后放行。

处理：v4 只用锁文件，不访问 7505。

### 4. 用 status.log 判断对方是否在线

现象：A 刚连上十几秒，B 一连日志出现 `STALE lock cleared (holder offline)`，B 也 ALLOW。

原因：`status /var/log/openvpn/status.log` 默认可能 60 秒才写一次，A 还没出现在文件里。

处理：锁产生后 90 秒内一律 DENY（`lock-fresh`），不看 status。

### 5. 被拒绝的 B 也会触发 client-disconnect

现象：B 先 `DENY`，紧接着 `UNLOCK released`，几秒后 B 重试变成 `ALLOW`，两人同时在线。

原因：OpenVPN 对失败的 client-connect 仍调用 disconnect。若 disconnect 无条件删锁，会把 A 的锁清掉。

处理（v4）：只有断开连接的 IP **和端口** 与锁里的持有人一致才删锁。B 被拒应看到 `UNLOCK skip rejected-or-other`。

### 6. 按源 IP 判断「是同一台设备」

现象：内网两台是 192.168.60.125 / 192.168.60.25，服务端 status 里却都是 `192.168.50.1`。

原因：出口 NAT。两边 `untrusted_ip` 相同，旧逻辑当成同一人重连而放行。

处理：用锁 + 端口区分会话，不把「相同源 IP」当作同一客户端。

### 7. 两台都断开后谁也连不上

现象：一直 `DENY holder=已经不存在的旧端口`，age 到几百秒。

原因：没有 `client-disconnect`，或 disconnect 没删对锁，锁一直留到 24 小时过期（更早版本）。

处理：配上 disconnect；v4 在锁超过 90 秒且 status 已无该 CN 时也可清陈旧锁。紧急恢复：

```bash
sudo rm -f /etc/openvpn/first-wins/locks/<证书名>.lock
```

### 8. 拷到服务器的不是最新脚本

现象：你以为已更新，日志仍是旧句子（如 `holder offline` 而没有 `v4` / `lock-fresh`）。

处理：部署后检查：

```bash
grep "HOOK start v4" /etc/openvpn/scripts/openvpn-first-wins.sh
```

客户端再连时日志必须出现 `HOOK start v4`。

---

## 回滚

```bash
sudo sed -i 's/^client-connect/#client-connect/' /etc/openvpn/server.conf
sudo sed -i 's/^client-disconnect/#client-disconnect/' /etc/openvpn/server.conf
sudo systemctl restart openvpn@server
```

如需恢复「后来的顶先来的」旧行为，再注释 `duplicate-cn`。

---

## 与其它功能

| 功能           | 关系                                               |
| -------------- | -------------------------------------------------- |
| 先连的赢       | 本脚本，同一证书只保留先连会话                     |
| 禁用           | CCD `disable`，谁都不能连                          |
| 踢下线（7505） | 拆当前隧道；若踢的是持有人，应走 disconnect 释放锁 |
| 撤销           | 证书作废                                           |

踢人后若锁未释放，手动删除对应 `locks/<证书名>.lock`。
# P1 改动说明（可 upgrade.sh，management 密码除外）

## 1. 装饰器

只保留 `routes/helpers.py`：

- `login_required`
- `roles_required(*roles)`
- `admin_required` = ADMIN + SUPER_ADMIN
- `super_admin_required`

`routes/auth/decorators.py` 改为从 helpers 再导出，避免两套实现。

JSON 未登录/无权限改为 `api_error`（带 `success/code/status/message`）。

## 2. 登录限流

两个登录入口都加了：

- `10/minute` 按 IP
- `5/minute` 按 `IP + username`

入口：

- `POST /auth/api/login`（页面登录）
- `POST /api/auth/login`

超限返回 429。测试时不要在短时间用错误密码打同一账号。

## 3. API envelope

`api_success` / `api_error` 现在都带：

```json
{ "success", "code", "msg", "message", "status", "data" }
```

`status` 为 `success` 或 `error`，旧前端读 `data.status` 仍可用。  
`modify_client_expiry` 已改为走这套函数。

## 4. 列表只读 + timer 写库

`GET /clients/data` 不再 `sync_*_to_db()`。在线状态仍用当前请求里的 7505 + ping overlay。

`sync_clients.py` 改为：

```text
create_app() + app_context
→ sync_openvpn_clients_to_db()
→ sync_online_state_to_db()
```

使用同一套 `models.py`。timer 进程设置 `VPNWM_SYNC_MODE=1`，启动时不导出 TC。

升级后确认：

```bash
sudo systemctl start sync_openvpn_clients.timer
sudo systemctl status sync_openvpn_clients.timer
```

## 5. Management 密码（需重启 OpenVPN，不要和 upgrade.sh 绑在一起）

代码已读取 `.env` 的 `OPENVPN_MGMT_PASSWORD`。未配置时仍兼容无密码管理口。

生产启用见 `scripts/README-management-password.md`。

## 测试建议（Web 部分）

```bash
bash ./upgrade.sh
```

1. 登录：错误密码连打，第 6 次左右应 429。  
2. 客户端列表、在线、踢人、筛选与升级前一致。  
3. 改到期、禁用仍返回 `message`。  
4. `journalctl -u sync_openvpn_clients.service -n 20` 无 traceback。
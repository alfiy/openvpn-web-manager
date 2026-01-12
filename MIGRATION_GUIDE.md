# OpenVPN Web Manager - 证书到期逻辑修改指南

## 修改概述

本次修改将证书到期管理逻辑从"吊销证书"改为"禁用用户登录",主要变更如下:

### 1. 核心变更

#### 1.1 证书有效期
- **之前**: 创建客户端时,用户指定证书有效期(如30天、90天等)
- **现在**: 所有客户端证书固定为**10年有效期**(3650天)

#### 1.2 到期管理
- **之前**: 到期后通过吊销证书(revoke)并重新颁发新证书来修改到期时间
- **现在**: 
  - 证书本身不吊销,保持10年有效期
  - 通过**逻辑到期时间**(`logical_expiry`)控制用户登录权限
  - 到期后自动禁用用户,阻止登录
  - 修改到期时间时,只需更新逻辑到期时间并重新启用用户

### 2. 数据库变更

#### 新增字段
在 `clients` 表中新增字段:
- `logical_expiry` (DATETIME): 逻辑到期时间,用于控制用户登录权限

#### 字段说明
- `expiry`: 证书真实到期时间(固定为创建后10年)
- `logical_expiry`: 逻辑到期时间(用户可配置,用于控制登录权限)
- `disabled`: 禁用标志(逻辑到期后自动设置为True)

### 3. 功能变更

#### 3.1 创建客户端 (`/api/clients/add`)
- 用户指定的 `expiry_days` 现在用于设置 `logical_expiry`
- 证书本身固定为10年有效期
- 返回信息包含逻辑到期时间和证书到期时间

**示例**:
```json
{
  "client_name": "user001",
  "expiry_days": 90
}
```
结果:
- 证书有效期: 10年(2025-12-28 至 2035-12-28)
- 逻辑到期时间: 90天(2025-12-28 至 2026-03-28)
- 90天后用户将被自动禁用

#### 3.2 修改到期时间 (`/api/clients/modify-expiry`)
- **之前**: 吊销旧证书 → 重新颁发新证书 → 清理index.txt
- **现在**: 
  - 只更新数据库中的 `logical_expiry` 字段
  - 自动重新启用用户(`disabled=False`)
  - 删除CCD禁用文件(如果存在)
  - **不再吊销和重新颁发证书**

#### 3.3 自动到期检查
在 `get_openvpn_clients()` 函数中:
- 检查每个客户端的 `logical_expiry`
- 如果当前时间超过逻辑到期时间:
  - 自动设置 `disabled=True`
  - 创建CCD禁用文件
  - 阻止客户端登录

### 4. 部署步骤

#### 4.1 备份数据库
```bash
sudo cp /opt/vpnwm/data/vpn_users.db /opt/vpnwm/data/vpn_users.db.backup
```

#### 4.2 运行迁移脚本
```bash
cd /workspace/uploads/openvpn-web-manager
sudo python3 migrate_add_logical_expiry.py
```

迁移脚本会:
- 添加 `logical_expiry` 字段
- 为现有客户端设置默认逻辑到期时间(1年后)

#### 4.3 重启服务
```bash
sudo systemctl restart openvpn-web-manager
```

### 5. 优势

#### 5.1 性能优化
- 不再需要吊销和重新颁发证书
- 减少了证书操作和index.txt清理的开销
- 修改到期时间响应更快

#### 5.2 证书稳定性
- 客户端证书保持不变(10年有效期)
- 避免了频繁的证书更新
- 减少了证书管理的复杂性

#### 5.3 灵活性
- 可以随时调整逻辑到期时间
- 到期后可快速重新启用
- 不影响证书本身的有效性

### 6. 注意事项

#### 6.1 现有客户端
- 迁移后,现有客户端的逻辑到期时间默认设置为1年后
- 建议根据实际需求调整每个客户端的逻辑到期时间

#### 6.2 证书到期
- 虽然证书有效期为10年,但实际登录权限由 `logical_expiry` 控制
- 10年后需要重新颁发证书(但这是一个长期的时间跨度)

#### 6.3 兼容性
- 客户端配置文件(.ovpn)不需要更新
- 现有的禁用/启用功能保持不变
- 与现有的CCD禁用机制完全兼容

### 7. API变更

#### 7.1 客户端列表 (`/api/clients`)
返回数据新增字段:
```json
{
  "id": 1,
  "name": "user001",
  "expiry": "2035-12-28T00:00:00",  // 证书真实到期时间
  "logical_expiry": "2026-03-28T00:00:00",  // 逻辑到期时间
  "online": true,
  "disabled": false,
  ...
}
```

#### 7.2 修改到期时间响应
```json
{
  "status": "success",
  "message": "客户端 user001 逻辑到期时间已修改为 90 天(到期日期: 2026-03-28),客户端已重新启用。"
}
```

### 8. 测试建议

1. **创建新客户端**: 验证证书有效期为10年,逻辑到期时间为指定天数
2. **修改到期时间**: 验证只更新逻辑到期时间,不吊销证书
3. **自动到期**: 将逻辑到期时间设置为过去时间,验证自动禁用功能
4. **重新启用**: 修改已到期客户端的到期时间,验证自动重新启用

### 9. 回滚方案

如需回滚到旧版本:
1. 恢复数据库备份: `sudo cp /opt/vpnwm/data/vpn_users.db.backup /opt/vpnwm/data/vpn_users.db`
2. 恢复旧版本代码文件
3. 重启服务

---

## 修改文件清单

- `models.py`: 添加 `logical_expiry` 字段
- `routes/api/add_client.py`: 修改创建客户端逻辑
- `routes/modify_client_expiry.py`: 修改到期时间管理逻辑
- `routes/api/clients.py`: 更新客户端列表返回数据
- `utils/openvpn_utils.py`: 添加自动到期检查逻辑
- `sync_clients.py`: 更新同步逻辑
- `migrate_add_logical_expiry.py`: 数据库迁移脚本(新增)
- `MIGRATION_GUIDE.md`: 迁移指南(新增)
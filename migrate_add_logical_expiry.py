#!/usr/bin/env python3
"""
数据库迁移脚本:添加 logical_expiry 字段
运行方式: python3 migrate_add_logical_expiry.py
"""
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# 数据库路径
DATA_DIR = "/opt/vpnwm/data"
DB_PATH = os.path.join(DATA_DIR, "vpn_users.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

def migrate():
    """添加 logical_expiry 字段到 clients 表"""
    try:
        engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
        
        with engine.connect() as conn:
            # 检查字段是否已存在
            result = conn.execute(text("PRAGMA table_info(clients)"))
            columns = [row[1] for row in result]
            
            if 'logical_expiry' in columns:
                print("✅ logical_expiry 字段已存在,无需迁移")
                return
            
            # 添加新字段
            print("🔄 开始添加 logical_expiry 字段...")
            conn.execute(text("ALTER TABLE clients ADD COLUMN logical_expiry DATETIME"))
            conn.commit()
            
            # 为现有客户端设置默认的逻辑到期时间(1年后)
            print("🔄 为现有客户端设置默认逻辑到期时间...")
            default_logical_expiry = datetime.now() + timedelta(days=365)
            conn.execute(
                text("UPDATE clients SET logical_expiry = :expiry WHERE logical_expiry IS NULL"),
                {"expiry": default_logical_expiry}
            )
            conn.commit()
            
            print("✅ 迁移完成!")
            print(f"   - 已添加 logical_expiry 字段")
            print(f"   - 现有客户端的逻辑到期时间已设置为: {default_logical_expiry.strftime('%Y-%m-%d')}")
            
    except SQLAlchemyError as e:
        print(f"❌ 数据库迁移失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        sys.exit(1)
    
    migrate()
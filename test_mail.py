import os
from flask import Flask
from flask_mail import Mail, Message
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# 邮件配置
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.qq.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 465)),
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'true').lower() in ('true', '1'),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'false').lower() in ('true', '1'),
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
)

# 初始化 Flask-Mail
mail = Mail(app)

def send_test_email(to_email):
    """发送测试邮件"""
    msg = Message(
        subject="OpenVPN 管理界面 - 测试邮件",
        recipients=[to_email],
        body="这是一封测试邮件，用于验证 Flask-Mail 配置是否正确。"
    )
    try:
        mail.send(msg)
        print(f"✅ 邮件发送成功: {to_email}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    with app.app_context():
        # 修改为你要测试的接收邮箱
        send_test_email("13012648@qq.com")

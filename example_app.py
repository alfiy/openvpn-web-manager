"""
示例应用 - 展示如何集成OpenVPN监控模块
"""

from flask import Flask
from openvpn_monitor import openvpn_bp

app = Flask(__name__)

# 注册OpenVPN监控蓝图
app.register_blueprint(openvpn_bp)


@app.route('/')
def index():
    """主页重定向到监控仪表板"""
    return """
    <html>
    <head>
        <title>OpenVPN 监控系统</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: #f8fafc;
            }
            .container {
                text-align: center;
            }
            h1 {
                color: #1e293b;
                margin-bottom: 20px;
            }
            a {
                display: inline-block;
                padding: 12px 24px;
                background: #2563eb;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 500;
            }
            a:hover {
                background: #1d4ed8;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔒 OpenVPN 监控系统</h1>
            <a href="/openvpn/dashboard">进入监控面板</a>
        </div>
    </body>
    </html>
    """


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
from flask import Flask
from routes.index import index_bp
from routes.install import install_bp
from routes.add_client import add_client_bp
from routes.revoke_client import revoke_client_bp
from routes.uninstall import uninstall_bp
from routes.download_client import download_client_bp
from routes.disconnect_client import disconnect_client_bp
from routes.modify_client_expiry import modify_client_expiry_bp
from routes.enable_client import enable_client_bp

app = Flask(__name__)
app.config['DEBUG'] = True

# 注册蓝图
app.register_blueprint(index_bp)
app.register_blueprint(install_bp)
app.register_blueprint(add_client_bp)
app.register_blueprint(revoke_client_bp)
app.register_blueprint(uninstall_bp)
app.register_blueprint(download_client_bp)
app.register_blueprint(disconnect_client_bp)
app.register_blueprint(modify_client_expiry_bp)
app.register_blueprint(enable_client_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)

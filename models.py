from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

    
class User(db.Model):
    __tablename__ = 'users'
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(64), unique=True, nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    password     = db.Column(db.String(128), nullable=False)
    reset_token  = db.Column(db.String(128))          # 找回密码令牌
    reset_expire = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw):
        self.password = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)
    
class Client(db.Model):
    __tablename__ = 'clients'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), unique=True, nullable=False)
    expiry       = db.Column(db.DateTime, nullable=True)
    online       = db.Column(db.Boolean, default=False)
    disabled     = db.Column(db.Boolean, default=False)
    vpn_ip       = db.Column(db.String(15), nullable=True)
    real_ip      = db.Column(db.String(15), nullable=True)
    duration     = db.Column(db.String(50), nullable=True)
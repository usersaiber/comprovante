from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Flag para administrador
    is_active = db.Column(db.Boolean, default=True)  # Campo para indicar se o usuário está ativo

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Métodos obrigatórios do Flask-Login
    def is_authenticated(self):
        return True

    def is_active(self):
        return self.is_active

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

class Name(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # Nome do pagador ou usuário

class Sector(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # Nome do setor

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sector_origin = db.Column(db.String(100), nullable=False)
    sector_destination = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    authorized = db.Column(db.Boolean, nullable=False)
    signature = db.Column(db.String(500), nullable=True)  # Assinatura desenhada (base64 ou URL)
    observations = db.Column(db.Text, nullable=True)
    submission_date = db.Column(db.DateTime, nullable=False, default=db.func.now())

    user = db.relationship('User', backref='receipts')
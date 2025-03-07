from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    __table_args__ = {"extend_existing": True}
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    otp_secret = db.Column(db.String(32), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_authenticated(self):
        return True

    def is_account_active(self):  # Renomeado para evitar conflito
        return self.is_active

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

class Name(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class Sector(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    
class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False)
    name_id = db.Column(db.Integer, db.ForeignKey('name.id', ondelete='RESTRICT'), nullable=False)
    sector_origin_id = db.Column(db.Integer, db.ForeignKey('sector.id', ondelete='RESTRICT'), nullable=False)
    sector_destination_id = db.Column(db.Integer, db.ForeignKey('sector.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    authorized = db.Column(db.Boolean, nullable=False)
    signature = db.Column(db.String(500), nullable=True)
    observations = db.Column(db.Text, nullable=True)
    submission_date = db.Column(db.DateTime, nullable=False, default=db.func.now())
    document_path = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        db.Index('idx_receipt_user_id', 'user_id'),
        db.Index('idx_receipt_name_id', 'name_id'),
    )

    user = db.relationship('User', backref='receipts')
    name = db.relationship('Name', backref='receipts')
    sector_origin = db.relationship('Sector', foreign_keys=[sector_origin_id], backref='origin_receipts')
    sector_destination = db.relationship('Sector', foreign_keys=[sector_destination_id], backref='destination_receipts')
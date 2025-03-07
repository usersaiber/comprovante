import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db
from models import User, Receipt, Name, Sector

with app.app_context():
    if os.path.exists('receipts.db'):
        os.remove('receipts.db')
    db.create_all()
    admin = User(username='cleiton', is_admin=True, is_active=True)
    admin.set_password('89198729')
    db.session.add(admin)
    db.session.add(Name(name='Cleiton Teixeira'))
    db.session.add(Name(name='Jéahn'))
    db.session.add(Sector(name='Equipamentos'))
    db.session.add(Sector(name='Rental'))
    db.session.add(Sector(name='Financeiro'))
    db.session.commit()
    print("Banco recriado com sucesso!")
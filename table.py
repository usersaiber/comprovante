from app import app, db
from models import User, Receipt, Name, Sector
import os  # Importar os para segurança

with app.app_context():
    # Remover o banco de dados existente, se existir
    if os.path.exists('receipts.db'):
        os.remove('receipts.db')

    # Criar novas tabelas com o schema atualizado
    db.create_all()

    # Adicionar dados de teste (se necessário)
    if not User.query.all():
        admin = User(username='cleiton', is_admin=True, is_active=True)
        admin.set_password('89198729')  # Ou a senha forte que você usa
        admin.otp_secret = None  # Adicionar otp_secret como None por padrão
        db.session.add(admin)
        db.session.commit()

    if not Name.query.all():
        db.session.add(Name(name='Cleiton Teixeira'))
        db.session.add(Name(name='Jéahn'))
        db.session.commit()

    if not Sector.query.all():
        db.session.add(Sector(name='Equipamentos'))
        db.session.add(Sector(name='Rental'))
        db.session.add(Sector(name='Financeiro'))
        db.session.commit()

    print("Tabelas criadas e dados de teste adicionados com sucesso!")
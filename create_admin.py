from app import app, db, User

with app.app_context():
    # Atualizar todos os usuários para is_active=True
    users = User.query.all()
    for user in users:
        if user.is_active is None:  # Se o campo não estiver definido
            user.is_active = True
    db.session.commit()
    print("Usuários atualizados com sucesso!")

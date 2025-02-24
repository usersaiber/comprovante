from flask import Flask, render_template, request, redirect, url_for, flash, send_file, json, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Receipt, Name, Sector
from datetime import datetime
import os
import base64
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet
import io
import csv
import smtplib
from email.mime.text import MIMEText
import pyotp
from flask import render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///receipts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'  # Substitua por uma chave segura
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Configurar para seu servidor de e-mail
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'seu_email@gmail.com'  # Substitua pelo seu e-mail
app.config['MAIL_PASSWORD'] = 'sua_senha_app'  # Use uma senha de aplicativo ou 2FA para Gmail

db.init_app(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Função de envio de e-mail (exemplo para Gmail)
def send_email(to, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = app.config['MAIL_USERNAME']
    msg['To'] = to

    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)

# Rotas existentes (mantidas como antes, com ajustes para novas funcionalidades)...

@app.route('/')
@login_required
def index():
    try:
        names = Name.query.all()  # Nomes disponíveis
        sectors = Sector.query.all()  # Setores disponíveis
        print(f"Nomes encontrados: {len(names)}, Setores encontrados: {len(sectors)}")  # Depuração
        return render_template('index.html', names=names, sectors=sectors)
    except Exception as e:
        flash(f'Erro ao carregar o formulário: {str(e)}', 'error')
        app.logger.error(f"Erro na rota /: {str(e)}")
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Verificar 2FA, se configurado
            if user.otp_secret:
                return redirect(url_for('setup_2fa'))
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

@app.route('/submit_receipt', methods=['POST'])
@login_required
def submit_receipt():
    try:
        print("Recebendo dados do formulário...")
        name_id = request.form.get('name')
        sector_origin_id = request.form.get('sector_origin')
        sector_destination_id = request.form.get('sector_destination')
        amount = request.form.get('amount')
        authorized = 'authorized' in request.form
        signature = request.form.get('signature', '')
        observations = request.form.get('observations', '')

        print(f"name_id: {name_id}, sector_origin_id: {sector_origin_id}, sector_destination_id: {sector_destination_id}, amount: {amount}, authorized: {authorized}, signature: {signature[:50]}..., observations: {observations}")

        if not all([name_id, sector_origin_id, sector_destination_id, amount]):
            raise ValueError("Campos obrigatórios ausentes")

        name = Name.query.get_or_404(name_id)
        sector_origin = Sector.query.get_or_404(sector_origin_id)
        sector_destination = Sector.query.get_or_404(sector_destination_id)
        amount = float(amount)

        new_receipt = Receipt(
            user_id=current_user.id,
            name=name.name,
            sector_origin=sector_origin.name,
            sector_destination=sector_destination.name,
            amount=amount,
            authorized=authorized,
            signature=signature,
            observations=observations
        )
        db.session.add(new_receipt)

        # Lidar com o upload de documentos
        if 'document' in request.files and request.files['document'].filename:
            document = request.files['document']
            if document and document.filename:
                document_path = os.path.join(app.static_folder, 'documents', document.filename)
                os.makedirs(os.path.join(app.static_folder, 'documents'), exist_ok=True)
                document.save(document_path)
                setattr(new_receipt, 'document_path', document_path)  # Usar setattr para setar o atributo
                print(f"Documento salvo em: {document_path}")
        db.session.commit()

        # Notificação por e-mail
        admin_email = 'admin@mantomac.com.br'
        subject = 'Novo Comprovante Submetido - Mantomac'
        body = f"Um novo comprovante foi submetido por {current_user.username} na Mantomac:\n\n" \
               f"Nome: {name.name}\nValor: R${amount:.2f}\nData: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        send_email(admin_email, subject, body)

        flash('Comprovante submetido com sucesso!', 'success')
        return jsonify({'status': 'success', 'redirect': url_for('index')})
    except Exception as e:
        flash(f'Erro ao submeter o comprovante: {str(e)}', 'error')
        app.logger.error(f"Erro na rota submit_receipt: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/admin_panel')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem acessar este painel.', 'error')
        return redirect(url_for('index'))
    
    try:
        receipts = Receipt.query.all()
        users = User.query.all()
        names = Name.query.all()  # ✅ Certifique-se de que esta linha existe
        sectors = Sector.query.all()
        return render_template('admin_panel.html', receipts=receipts, users=users, names=names, sectors=sectors)
    except Exception as e:
        flash(f'Erro ao carregar o painel administrativo: {str(e)}', 'error')
        return redirect(url_for('index'))



@app.route('/filter_receipts', methods=['GET'])
@login_required
def filter_receipts():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem filtrar comprovantes.', 'error')
        return redirect(url_for('admin_panel'))
    
    user_id = request.args.get('user_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')
    authorized = request.args.get('authorized')

    query = Receipt.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Receipt.submission_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Receipt.submission_date <= datetime.strptime(end_date, '%Y-%m-%d'))
    if min_amount:
        query = query.filter(Receipt.amount >= float(min_amount))
    if max_amount:
        query = query.filter(Receipt.amount <= float(max_amount))
    if authorized:
        query = query.filter_by(authorized=(authorized == 'true'))

    receipts = query.all()
    return render_template('admin_panel.html', receipts=receipts, users=User.query.all(), names=Name.query.all(), sectors=Sector.query.all())

@app.route('/export_csv')
@login_required
def export_csv():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem exportar para CSV.', 'error')
        return redirect(url_for('admin_panel'))
    
    receipts = Receipt.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Usuário', 'Nome', 'Setor Origem', 'Setor Destino', 'Valor (R$)', 'Autorizado', 'Assinatura', 'Data'])
    for receipt in receipts:
        user = User.query.get(receipt.user_id)
        writer.writerow([
            receipt.id,
            user.username if user else 'Usuário não encontrado',
            receipt.name,
            receipt.sector_origin,
            receipt.sector_destination,
            f'{receipt.amount:.2f}',
            'Sim' if receipt.authorized else 'Não',
            receipt.signature or 'Não informada',
            receipt.submission_date.strftime('%d/%m/%Y %H:%M') if receipt.submission_date else 'Data não informada'
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name='comprovantes_mantomac.csv',
        mimetype='text/csv'
    )

@app.route('/edit_name/<int:name_id>', methods=['GET', 'POST'])
@login_required
def edit_name(name_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar nomes.', 'error')
        return redirect(url_for('admin_panel'))
    
    name = Name.query.get_or_404(name_id)
    if request.method == 'POST':
        name.name = request.form['name']
        db.session.commit()
        flash('Nome editado com sucesso!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('edit_name.html', name=name)

@app.route('/sector/edit/<int:sector_id>', methods=['GET', 'POST'])
@login_required
def edit_sector(sector_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar setores.', 'error')
        return redirect(url_for('admin_panel'))

    sector = Sector.query.get_or_404(sector_id)  # Busca o setor pelo ID no banco de dados

    if request.method == 'POST':
        sector.name = request.form['name']  # Atualiza o nome do setor com o valor do formulário
        db.session.commit()  # Salva as alterações no banco de dados
        flash("Setor atualizado com sucesso!", "success")
        return redirect(url_for('admin_panel'))  # Redireciona para o painel do admin

    return render_template('edit_sector.html', sector=sector)  # Renderiza o formulário para edição

@app.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar usuários.', 'error')
        return redirect(url_for('admin_panel'))

    user = User.query.get_or_404(user_id)  # Obtém o usuário pelo ID

    if request.method == 'POST':
        user.username = request.form['username']
        if request.form['password']:
            user.set_password(request.form['password'])  # Atualiza a senha se fornecida
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('admin_panel'))  # Retorna ao painel do admin

    return render_template('edit_user.html', user=user)


@app.route('/2fa_setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if request.method == 'POST':
        secret = pyotp.random_base32()
        user = current_user
        user.otp_secret = secret
        db.session.commit()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(user.username, issuer_name="Mantomac Comprovantes")
        return render_template('2fa_setup.html', uri=uri, secret=secret)
    return render_template('2fa_setup.html')

@app.route('/2fa_verify', methods=['POST'])
@login_required
def verify_2fa():
    secret = current_user.otp_secret
    code = request.form['code']
    if pyotp.TOTP(secret).verify(code):
        flash('Autenticação de dois fatores configurada com sucesso!', 'success')
        return redirect(url_for('index'))
    flash('Código inválido. Tente novamente.', 'error')
    return redirect(url_for('setup_2fa'))

# Rotas de exclusão e criação (mantidas como antes)...

@app.route('/create_name', methods=['POST'])
@login_required
def create_name():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem criar nomes.', 'error')
        return redirect(url_for('admin_panel'))
    
    name = request.form['name']
    if Name.query.filter_by(name=name).first():
        flash('Nome já existe.', 'error')
    else:
        new_name = Name(name=name)
        db.session.add(new_name)
        db.session.commit()
        flash('Nome criado com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/create_sector', methods=['POST'])
@login_required
def create_sector():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem criar setores.', 'error')
        return redirect(url_for('admin_panel'))
    
    sector = request.form['sector']
    if Sector.query.filter_by(name=sector).first():
        flash('Setor já existe.', 'error')
    else:
        new_sector = Sector(name=sector)
        db.session.add(new_sector)
        db.session.commit()
        flash('Setor criado com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/create_user', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem criar usuários.', 'error')
        return redirect(url_for('index'))
    
    username = request.form['username']
    password = request.form['password']
    if User.query.filter_by(username=username).first():
        flash('Usuário já existe.', 'error')
    else:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir usuários.', 'error')
        return redirect(url_for('admin_panel'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Usuário excluído com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_name/<int:name_id>', methods=['POST'])
@login_required
def delete_name(name_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir nomes.', 'error')
        return redirect(url_for('admin_panel'))
    
    name = Name.query.get_or_404(name_id)
    db.session.delete(name)
    db.session.commit()
    flash('Nome excluído com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_sector/<int:sector_id>', methods=['POST'])
@login_required
def delete_sector(sector_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir setores.', 'error')
        return redirect(url_for('admin_panel'))
    
    sector = Sector.query.get_or_404(sector_id)
    db.session.delete(sector)
    db.session.commit()
    flash('Setor excluído com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_receipt/<int:receipt_id>', methods=['POST'])
@login_required
def delete_receipt(receipt_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir comprovantes.', 'error')
        return redirect(url_for('admin_panel'))
    
    receipt = Receipt.query.get_or_404(receipt_id)
    db.session.delete(receipt)
    db.session.commit()
    flash('Comprovante excluído com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/download_pdf')
@login_required
def download_pdf():
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem baixar o relatório.', 'error')
        return redirect(url_for('admin_panel'))
    
    # Criar o PDF
    pdf_buffer = generate_pdf()
    
    # Enviar o PDF como arquivo para download
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name='relatorio_comprovantes_mantomac.pdf',
        mimetype='application/pdf'
    )

def generate_pdf():
    # Criar um buffer para o PDF em modo retrato (ajustado para legibilidade)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    elements = []

    # Estilos
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    title_style = styles['Heading1']
    title_style.textColor = colors.HexColor('#0000b8')  # Nova cor primária (verde esmeralda)

    # Adicionar logotipo
    logo_path = os.path.join(app.static_folder, 'logo.jpg')
    if os.path.exists(logo_path):
        img = Image(logo_path, width=150, height=75)  # Ajuste o tamanho conforme necessário
        elements.append(img)
    else:
        elements.append(Paragraph("Logotipo não encontrado", title_style))

    # Título do relatório
    elements.append(Paragraph("Relatório de Comprovantes de Recebimento - Mantomac", title_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Paragraph(f"Gerenciado por Cleiton Teixeira - TI Mantomac", normal_style))
    elements.append(Paragraph("<br/><br/>", normal_style))

    # Dados dos comprovantes
    receipts = Receipt.query.all()
    if receipts:
        data = [['ID', 'Usuário', 'Nome', 'Setor Origem', 'Setor Destino', 'Valor (R$)', 'Autorizado', 'Assinatura', 'Data']]
        for receipt in receipts:
            user = User.query.get(receipt.user_id)
            # Verificar e corrigir os campos "ID", "Usuário" e "Nome"
            receipt_id = str(receipt.id) if receipt.id else 'N/A'
            user_name = user.username if user else 'Usuário não encontrado'
            receipt_name = receipt.name if receipt.name else 'Não informado'

            # Processar a assinatura base64 para imagem
            signature_image = None
            if receipt.signature and receipt.signature.startswith('data:image/png;base64,'):
                try:
                    # Extrair a parte base64 da string (remover "data:image/png;base64,")
                    base64_string = receipt.signature.split(',')[1]
                    # Decodificar base64 para bytes
                    img_data = base64.b64decode(base64_string)
                    # Criar um buffer temporário para a imagem
                    img_buffer = io.BytesIO(img_data)
                    # Criar uma imagem para o reportlab
                    signature_image = Image(img_buffer, width=100, height=50)  # Ajuste o tamanho para melhor visualização
                except Exception as e:
                    print(f"Erro ao processar assinatura: {e}")
                    signature_image = Paragraph("Assinatura não processada", normal_style)
            elif receipt.signature:
                signature_image = Paragraph(receipt.signature or 'Não informada', normal_style)
            else:
                signature_image = Paragraph('Não informada', normal_style)

            data.append([
                receipt_id,  # Corrigido para garantir que o ID não seja None
                user_name,  # Corrigido para garantir que o usuário seja exibido
                receipt_name,  # Corrigido para garantir que o nome não seja None
                receipt.sector_origin or 'Não informado',
                receipt.sector_destination or 'Não informado',
                f'{receipt.amount:.2f}' if receipt.amount else '0.00',
                'Sim' if receipt.authorized else 'Não',
                signature_image,  # Usar a imagem processada ou texto
                receipt.submission_date.strftime('%d/%m/%Y %H:%M') if receipt.submission_date else 'Data não informada'
            ])

        # Criar tabela com colunas ajustadas para modo retrato
        table = Table(data, colWidths=[40, 80, 80, 80, 80, 60, 60, 120, 70])  # Ajuste os tamanhos para legibilidade
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ECC71')),  # Nova cor primária (verde esmeralda)
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Texto branco no cabeçalho
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),  # Nova fonte moderna
            ('FONTSIZE', (0, 0), (-1, -1), 12),  # Tamanho de fonte ajustado
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),  # Mais espaço
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # Linhas em branco
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # Texto preto para legibilidade
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#2ECC71')),  # Grade em verde esmeralda
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')  # Alinhamento vertical no meio
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Nenhum comprovante encontrado.", normal_style))

    # Gerar o PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas no banco de dados
    app.run(debug=True, host='0.0.0.0', port=5000)
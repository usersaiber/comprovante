from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, make_response
from werkzeug.utils import secure_filename
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
from email.mime.multipart import MIMEMultipart
import pyotp
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from dotenv import load_dotenv
import logging
import ssl
from functools import wraps

app = Flask(__name__)
load_dotenv()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'Login'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso negado. Apenas administradores podem acessar essa página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///receipts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sua_chave_secreta_aqui')
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'mail.mantomac.com.br')
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'cleiton.teixeira@mantomac.com.br')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '89198729')
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'documents')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db.init_app(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Função de envio de e-mail
def send_email(to, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = app.config['MAIL_USERNAME']
    msg['To'] = to

    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)

@app.route('/')
@login_required
def index():
    try:
        names = Name.query.all()
        sectors = Sector.query.all()
        logger.info(f"Nomes encontrados: {len(names)}, Setores encontrados: {len(sectors)}")
        return render_template('index.html', names=names, sectors=sectors)
    except Exception as e:
        flash(f'Erro ao carregar o formulário: {str(e)}', 'error')
        logger.error(f"Erro na rota /: {str(e)}")
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
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

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'png'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/submit_receipt', methods=['POST'])
@login_required
def submit_receipt():
    try:
        logger.info("Recebendo dados do formulário...")
        name_id = request.form.get('name')
        sector_origin_id = request.form.get('sector_origin')
        sector_destination_id = request.form.get('sector_destination')
        amount = request.form.get('amount')
        authorized = 'authorized' in request.form
        signature = request.form.get('signature', '')
        observations = request.form.get('observations', '')
        document = request.files.get('document')

        logger.info(f"name_id: {name_id}, sector_origin_id: {sector_origin_id}, sector_destination_id: {sector_destination_id}, amount: {amount}, authorized: {authorized}, signature: {signature[:50]}..., observations: {observations}")

        if not all([name_id, sector_origin_id, sector_destination_id, amount]):
            raise ValueError("Campos obrigatórios ausentes")

        try:
            amount = float(amount)
        except ValueError:
            raise ValueError("O campo 'amount' deve ser um número válido")

        name = Name.query.get_or_404(name_id)
        sector_origin = Sector.query.get_or_404(sector_origin_id)
        sector_destination = Sector.query.get_or_404(sector_destination_id)

        new_receipt = Receipt(
            user_id=current_user.id,
            name_id=name_id,
            sector_origin_id=sector_origin_id,
            sector_destination_id=sector_destination_id,
            amount=amount,
            authorized=authorized,
            signature=signature,
            observations=observations
        )

        # Handle document upload only if a valid document is provided
        if document and document.filename:
            if not allowed_file(document.filename):
                flash('Tipo de arquivo não permitido.', 'danger')
                return jsonify({'status': 'error', 'message': 'Tipo de arquivo não permitido'}), 400
            filename = secure_filename(document.filename)
            document_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            logger.info(f"Tentando salvar em: {document_path}")
            document.save(document_path)
            new_receipt.document_path = f'documents/{filename}'
        else:
            new_receipt.document_path = None  # No document uploaded

        db.session.add(new_receipt)
        db.session.commit()

        admin_email = app.config['MAIL_USERNAME']
        subject = 'Novo Comprovante Submetido - Mantomac'
        body = f"Um novo comprovante foi submetido por {current_user.username} na Mantomac:\n\n" \
               f"Nome: {name.name}\nValor: R${amount:.2f}\nData: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        send_email(admin_email, subject, body)

        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        flash('Comprovante submetido com sucesso!', 'success')
        return jsonify({'status': 'success', 'redirect': url_for('index')})
    except Exception as e:
        logger.error(f"Erro ao submeter comprovante: {e}")
        flash(f'Erro ao submeter comprovante: {str(e)}', 'danger')
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/admin_panel')
@login_required
@admin_required
def admin_panel():
    sectors = Sector.query.all()  # Busca todos os setores
    names = Name.query.all()      # Busca todos os nomes
    receipts = Receipt.query.all()
    users = User.query.all()  # Garantir que users seja passado
    return render_template('admin_panel.html', receipts=receipts, users=users, sectors=sectors, names=names)
    

@app.route('/edit_receipt/<int:receipt_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_receipt(receipt_id):
    receipt = Receipt.query.get_or_404(receipt_id)
    sectors = Sector.query.all()
    names = Name.query.all()
    if request.method == 'POST':
        receipt.name_id = request.form.get('name')
        receipt.sector_origin_id = request.form.get('sector_origin')
        receipt.sector_destination_id = request.form.get('sector_destination')
        receipt.amount = float(request.form.get('amount'))
        receipt.authorized = 'authorized' in request.form
        receipt.signature = request.form.get('signature', receipt.signature)
        receipt.observations = request.form.get('observations', receipt.observations)
        document = request.files.get('document')
        if document and document.filename:
            filename = secure_filename(document.filename)
            document_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(document.filename))

            document.save(document_path)
            receipt.document_path = f'documents/{filename}'
        db.session.commit()
        flash('Comprovante atualizado com sucesso!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('edit_receipt.html', receipt=receipt, sectors=sectors, names=names)

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
@admin_required
def export_csv():
    receipts = Receipt.query.all()
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    
    # Escrever o cabeçalho
    writer.writerow(['ID', 'Usuário', 'Nome', 'Setor Origem', 'Setor Destino', 'Valor (R$)', 'Autorizado', 'Assinatura', 'Data', 'Documento'])
    
    # Escrever os dados
    for receipt in receipts:
        user = User.query.get(receipt.user_id)
        user_name = user.username if user else 'Usuário não encontrado'
        receipt_name = receipt.name.name if receipt.name else 'Não informado'
        sector_origin = receipt.sector_origin.name if receipt.sector_origin else 'Não informado'
        sector_destination = receipt.sector_destination.name if receipt.sector_destination else 'Não informado'
        amount = f'{receipt.amount:.2f}' if receipt.amount is not None else '0.00'
        authorized = 'Sim' if receipt.authorized else 'Não'
        signature = 'Sim' if receipt.signature else 'Não'
        submission_date = receipt.submission_date.strftime('%d/%m/%Y %H:%M') if receipt.submission_date else 'Não informada'
        document = receipt.document_path if receipt.document_path else 'Nenhum documento anexado'
        
        writer.writerow([receipt.id, user_name, receipt_name, sector_origin, sector_destination, amount, authorized, signature, submission_date, document])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='comprovantes.csv'  # Corrigido para download_name
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

    sector = Sector.query.get_or_404(sector_id)

    if request.method == 'POST':
        sector.name = request.form['name']
        db.session.commit()
        flash("Setor atualizado com sucesso!", "success")
        return redirect(url_for('admin_panel'))

    return render_template('edit_sector.html', sector=sector)

@app.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem editar usuários.', 'error')
        return redirect(url_for('admin_panel'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.username = request.form['username']
        if request.form['password']:
            user.set_password(request.form['password'])
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('admin_panel'))

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
@admin_required
def create_user():
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') in ['true', 'on']  # Checkbox marcado retorna "on" ou "true"
    is_active = request.form.get('is_active') in ['true', 'on']  # Checkbox marcado retorna "on" ou "true"

    if not username:
        flash('Usuário é obrigatório!', 'danger')
        return redirect(url_for('admin_panel'))
    if User.query.filter_by(username=username).first():
        flash('Usuário já existe!', 'danger')
        return redirect(url_for('admin_panel'))

    new_user = User(username=username, is_admin=is_admin, is_active=is_active)
    if password:  # Apenas define senha se fornecida
        new_user.set_password(password)  # Assumindo que set_password está implementado
    db.session.add(new_user)
    db.session.commit()
    flash('Usuário criado com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_receipt/<int:receipt_id>', methods=['POST'])
@login_required
def delete_receipt(receipt_id):
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem excluir comprovantes.', 'error')
        return redirect(url_for('admin_panel'))
    
    receipt = Receipt.query.get_or_404(receipt_id)
    logger.info(f"Deletando comprovante ID: {receipt.id}, Nome: {receipt.name}")
    db.session.delete(receipt)
    db.session.commit()
    flash('Comprovante excluído com sucesso!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Acesso negado.', 'error')
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

@app.route('/download_pdf')
@login_required
@admin_required
def download_pdf():
    buffer = generate_pdf()
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=relatorio_comprovantes.pdf'
    return response

def generate_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    elements = []

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    title_style = styles['Heading1']
    title_style.textColor = colors.HexColor('#0041FF')  # Azul da Mantomac
    title_style.alignment = 1  # Centralizar
    title_style.fontSize = 14  # Reduzido para 14pt
    normal_style.fontName = 'Roboto' if 'Roboto' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
    normal_style.alignment = 1  # Centralizar
    normal_style.fontSize = 10  # Reduzido para 10pt

    # Logo
    logo_path = os.path.join(app.static_folder, 'logo.jpg')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=150, height=75)
        logo.hAlign = 'CENTER'
        elements.append(logo)
    else:
        elements.append(Paragraph("Logotipo não encontrado", title_style))
    elements.append(Paragraph("<br/>", normal_style))

    # Título e informações
    elements.append(Paragraph("Relatório de Comprovantes de Recebimento - Mantomac", title_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Paragraph("Gerenciado por Cleiton Teixeira - TI Mantomac", normal_style))
    elements.append(Paragraph("<br/><br/>", normal_style))

    # Tabela de comprovantes
    receipts = Receipt.query.all()
    if receipts:
        data = [['ID', 'Usuário', 'Nome', 'Setor Origem', 'Setor Destino', 'Valor (R$)', 'Autorizado', 'Assinatura', 'Data']]
        for receipt in receipts:
            user = User.query.get(receipt.user_id)
            receipt_id = str(receipt.id) if receipt.id else 'N/A'
            user_name = user.username if user else 'Usuário não encontrado'
            receipt_name = receipt.name.name if receipt.name else 'Não informado'
            receipt_sector_origin = receipt.sector_origin.name if receipt.sector_origin else 'Não informado'
            receipt_sector_destination = receipt.sector_destination.name if receipt.sector_destination else 'Não informado'

            signature_content = Paragraph("Ver Assinatura no Sistema", normal_style)

            data.append([
                receipt_id,
                user_name,
                receipt_name,
                receipt_sector_origin,
                receipt_sector_destination,
                f'R${receipt.amount:.2f}' if receipt.amount is not None else 'R$0.00',
                'Sim' if receipt.authorized else 'Não',
                signature_content,
                receipt.submission_date.strftime('%d/%m/%Y %H:%M') if receipt.submission_date else 'Data não informada'
            ])

        table = Table(data, colWidths=[30, 70, 100, 80, 80, 60, 60, 100, 90])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0041FF')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Roboto' if 'Roboto' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),  # Cabeçalho reduzido para 10pt
            ('FONTSIZE', (0, 1), (-1, -1), 8),  # Corpo da tabela reduzido para 8pt
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#0a2355')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#0041FF')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F5F6FA'), colors.white])
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Nenhum comprovante encontrado.", normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
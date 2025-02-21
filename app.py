from flask import Flask, render_template, request, redirect, url_for, flash, send_file, json
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Receipt, Name, Sector
from datetime import datetime
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet
import io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///receipts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'  # Substitua por uma chave segura

db.init_app(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    names = Name.query.all()  # Nomes disponíveis
    sectors = Sector.query.all()  # Setores disponíveis
    return render_template('index.html', names=names, sectors=sectors)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
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
    name_id = request.form['name']  # ID do nome selecionado
    sector_origin_id = request.form['sector_origin']  # ID do setor de origem
    sector_destination_id = request.form['sector_destination']  # ID do setor de destino
    amount = float(request.form['amount'])
    authorized = 'authorized' in request.form
    signature = request.form.get('signature', '')  # Assinatura desenhada em base64
    observations = request.form.get('observations', '')

    name = Name.query.get_or_404(name_id)
    sector_origin = Sector.query.get_or_404(sector_origin_id)
    sector_destination = Sector.query.get_or_404(sector_destination_id)

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
    db.session.commit()

    flash('Comprovante submetido com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/admin_panel')
@login_required
def admin_panel():
    print(f"Current user: {current_user.username if current_user.is_authenticated else 'None'}")  # Depuração
    if not current_user.is_admin:
        flash('Acesso negado. Apenas administradores podem acessar este painel.', 'error')
        return redirect(url_for('index'))
    
    try:
        receipts = Receipt.query.all()
        users = User.query.all()
        names = Name.query.all()
        sectors = Sector.query.all()
        return render_template('admin_panel.html', receipts=receipts, users=users, names=names, sectors=sectors)
    except Exception as e:
        flash(f'Erro ao carregar o painel administrativo: {str(e)}', 'error')
        return redirect(url_for('index'))

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
        download_name='relatorio_comprovantes.pdf',
        mimetype='application/pdf'
    )

def generate_pdf():
    # Criar um buffer para o PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    elements = []

    # Estilos
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    title_style = styles['Heading1']
    title_style.textColor = colors.HexColor('#0041FF')  # Azul principal da marca

    # Adicionar logotipo
    logo_path = os.path.join(app.static_folder, 'logo.jpg')
    if os.path.exists(logo_path):
        img = Image(logo_path, width=150, height=75)  # Ajuste o tamanho conforme necessário
        elements.append(img)
    else:
        elements.append(Paragraph("Logotipo não encontrado", title_style))

    # Título do relatório
    elements.append(Paragraph("Relatório de Comprovantes de Recebimento", title_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Paragraph(f"Gerenciado por Cleiton Teixeira - TI Mantoma", normal_style))
    elements.append(Paragraph("<br/><br/>", normal_style))

    # Dados dos comprovantes
    receipts = Receipt.query.all()
    if receipts:
        data = [['ID', 'Usuário', 'Nome', 'Setor Origem', 'Setor Destino', 'Valor (R$)', 'Autorizado', 'Assinatura', 'Data']]
        for receipt in receipts:
            user = User.query.get(receipt.user_id)
            data.append([
                str(receipt.id),
                user.username if user else 'Usuário não encontrado',
                receipt.name,
                receipt.sector_origin,
                receipt.sector_destination,
                f'{receipt.amount:.2f}',
                'Sim' if receipt.authorized else 'Não',
                receipt.signature or 'Não informada',
                receipt.submission_date.strftime('%d/%m/%Y %H:%M')
            ])

        # Criar tabela
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0041FF')),  # Cabeçalho em azul
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Texto branco no cabeçalho
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # Linhas em branco
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # Texto preto para legibilidade
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#0041FF'))  # Grade em azul
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
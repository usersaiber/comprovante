import sqlite3

# Conectar ao banco de dados
conn = sqlite3.connect('receipts.db')
cursor = conn.cursor()

# Verificar as colunas da tabela 'receipt'
cursor.execute("PRAGMA table_info(receipt);")
columns = cursor.fetchall()

# Verificar se a coluna 'document_path' já existe
if not any(col[1] == 'document_path' for col in columns):
    # Adicionar a coluna 'document_path' se não existir
    cursor.execute("ALTER TABLE receipt ADD COLUMN document_path TEXT;")
    print("Coluna 'document_path' adicionada com sucesso.")
else:
    print("A coluna 'document_path' já existe.")

# Salvar as alterações e fechar a conexão
conn.commit()
conn.close()

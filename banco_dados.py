import sqlite3
import pandas as pd
import uuid
from datetime import datetime

DB_NAME = "sistema_subestacao.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nome TEXT,
            login TEXT UNIQUE,
            senha TEXT,
            permissao TEXT
        )
    ''')
    
    # --- VACINA DE CORREÇÃO ---
    # Transforma o usuário criado na versão anterior de 'admin' para 'adm'
    cursor.execute("UPDATE usuarios SET permissao = 'adm' WHERE permissao = 'admin'")
    # --------------------------
    
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        id_admin = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO usuarios (id, nome, login, senha, permissao)
            VALUES (?, ?, ?, ?, ?)
        ''', (id_admin, 'Administrador', 'admin', 'admin123', 'adm'))
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS medicoes (
            id TEXT PRIMARY KEY,
            lote TEXT,
            svc TEXT,
            harmonica TEXT,
            serial TEXT,
            referencia REAL,
            medicao_1 REAL,
            analise REAL,
            sincronizado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_trocas (
            id TEXT PRIMARY KEY,
            lote TEXT,
            svc TEXT,
            harmonica TEXT,
            cap1 TEXT,
            cap2 TEXT,
            data_troca TEXT,
            sincronizado INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def validar_login(login, senha):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, login, permissao FROM usuarios WHERE login=? AND senha=?", (login, senha))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "nome": user[1], "login": user[2], "permissao": user[3]}
    return None

def listar_usuarios():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, login, permissao FROM usuarios ORDER BY nome")
    cols = ['id', 'nome', 'login', 'permissao']
    dados = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()
    return dados

def criar_usuario(nome, login, permissao):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM usuarios WHERE login=?", (login,))
        if cursor.fetchone():
            return False, "O código de usuário (login) já existe."
        
        id_uuid = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO usuarios (id, nome, login, senha, permissao)
            VALUES (?, ?, ?, '123', ?)
        ''', (id_uuid, nome, login, permissao))
        conn.commit()
        return True, "Usuário criado com sucesso!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def excluir_usuario(id_usuario):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id_usuario,))
    conn.commit()
    conn.close()

def salvar_planilha_sql(df, lote_nome, svc_nome):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM medicoes WHERE lote = ? AND svc = ?", (lote_nome, svc_nome))
    cursor.execute("DELETE FROM registro_trocas WHERE lote = ? AND svc = ?", (lote_nome, svc_nome))
    
    for index, row in df.iterrows():
        serial_raw = str(row.iloc[0]).strip()
        if not serial_raw or serial_raw == 'nan':
            continue
            
        id_uuid = str(uuid.uuid4())
        serial = serial_raw
        harmonica = serial.split('-')[0] if '-' in serial else ""
        
        ref_raw = str(row.iloc[2]).replace(',', '.')
        referencia = float(ref_raw) if ref_raw and ref_raw != 'nan' else None
        
        med_raw = str(row.iloc[3]).replace(',', '.')
        medicao_1 = float(med_raw) if med_raw and med_raw != 'nan' else None
        
        analise = medicao_1
        
        cursor.execute('''
            INSERT INTO medicoes (id, lote, svc, harmonica, serial, referencia, medicao_1, analise, sincronizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (id_uuid, lote_nome, svc_nome, harmonica, serial, referencia, medicao_1, analise))
        
    conn.commit()
    conn.close()

def listar_lotes_salvos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT lote FROM medicoes ORDER BY lote DESC")
    lotes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return lotes

def buscar_dados_diagrama(lote, svc, harmonica):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT serial, referencia, medicao_1, analise 
        FROM medicoes 
        WHERE lote = ? AND svc = ? AND harmonica = ?
    ''', (lote, svc, harmonica))
    
    dados = cursor.fetchall()
    conn.close()
    
    resultado = {}
    for linha in dados:
        serial, ref, med1, analise = linha
        resultado[serial] = {
            "referencia": ref,
            "medicao_1": med1,
            "analise": analise
        }
    return resultado

def listar_historico():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT lote, svc, COUNT(serial) as qtd_capacitores
        FROM medicoes
        GROUP BY lote, svc
        ORDER BY lote DESC
    ''')
    historico = [{"lote": row[0], "svc": row[1], "qtd": row[2]} for row in cursor.fetchall()]
    conn.close()
    return historico

def excluir_lote(lote, svc):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM medicoes WHERE lote = ? AND svc = ?", (lote, svc))
    cursor.execute("DELETE FROM registro_trocas WHERE lote = ? AND svc = ?", (lote, svc))
    conn.commit()
    conn.close()

def efetivar_troca(lote, svc, harmonica, cap1_serial, cap2_serial):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT medicao_1, analise FROM medicoes WHERE lote=? AND svc=? AND harmonica=? AND serial=?", (lote, svc, harmonica, cap1_serial))
    val1 = cursor.fetchone()
    
    cursor.execute("SELECT medicao_1, analise FROM medicoes WHERE lote=? AND svc=? AND harmonica=? AND serial=?", (lote, svc, harmonica, cap2_serial))
    val2 = cursor.fetchone()
    
    if val1 and val2:
        cursor.execute("UPDATE medicoes SET medicao_1=?, analise=?, sincronizado=0 WHERE lote=? AND svc=? AND harmonica=? AND serial=?", (val2[0], val2[1], lote, svc, harmonica, cap1_serial))
        cursor.execute("UPDATE medicoes SET medicao_1=?, analise=?, sincronizado=0 WHERE lote=? AND svc=? AND harmonica=? AND serial=?", (val1[0], val1[1], lote, svc, harmonica, cap2_serial))
        
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        id_log = str(uuid.uuid4())
        
        cursor.execute('''
            INSERT INTO registro_trocas (id, lote, svc, harmonica, cap1, cap2, data_troca, sincronizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        ''', (id_log, lote, svc, harmonica, cap1_serial, cap2_serial, agora))
        
    conn.commit()
    conn.close()

def buscar_dados_brutos(lote, svc):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT serial, harmonica, referencia, medicao_1 FROM medicoes WHERE lote=? AND svc=? ORDER BY harmonica, serial", (lote, svc))
    cols = ['serial', 'harmonica', 'referencia', 'medicao_1']
    dados = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()
    return dados

def buscar_logs_troca(lote, svc):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT data_troca, harmonica, cap1, cap2 FROM registro_trocas WHERE lote=? AND svc=? ORDER BY id DESC", (lote, svc))
    cols = ['data_troca', 'harmonica', 'cap1', 'cap2']
    dados = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()
    return dados

def obter_dados_nao_sincronizados():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medicoes WHERE sincronizado = 0")
    medicoes = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM registro_trocas WHERE sincronizado = 0")
    trocas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"medicoes": medicoes, "trocas": trocas}

def marcar_como_sincronizados(medicoes_ids, trocas_ids):
    if not medicoes_ids and not trocas_ids: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if medicoes_ids:
        placeholders = ','.join(['?'] * len(medicoes_ids))
        cursor.execute(f"UPDATE medicoes SET sincronizado = 1 WHERE id IN ({placeholders})", medicoes_ids)
    if trocas_ids:
        placeholders = ','.join(['?'] * len(trocas_ids))
        cursor.execute(f"UPDATE registro_trocas SET sincronizado = 1 WHERE id IN ({placeholders})", trocas_ids)
    conn.commit()
    conn.close()

def obter_todos_dados_nuvem():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medicoes")
    medicoes = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM registro_trocas")
    trocas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"medicoes": medicoes, "trocas": trocas}

def mesclar_dados_recebidos(dados):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for m in dados.get("medicoes", []):
        cursor.execute('''
            INSERT OR REPLACE INTO medicoes 
            (id, lote, svc, harmonica, serial, referencia, medicao_1, analise, sincronizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (m['id'], m['lote'], m['svc'], m['harmonica'], m['serial'], m['referencia'], m['medicao_1'], m['analise']))
        
    for t in dados.get("trocas", []):
        cursor.execute('''
            INSERT OR REPLACE INTO registro_trocas 
            (id, lote, svc, harmonica, cap1, cap2, data_troca, sincronizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ''', (t['id'], t['lote'], t['svc'], t['harmonica'], t['cap1'], t['cap2'], t['data_troca']))
        
    conn.commit()
    conn.close()
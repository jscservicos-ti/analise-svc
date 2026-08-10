from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps
import pandas as pd
import banco_dados
import traceback
import urllib.request
import json
import sys
import os
import threading
try:
    import webview
except ImportError:
    pass  # Ignora silenciosamente no servidor Linux, pois lá não precisamos de janelas

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__, template_folder=resource_path('templates'))
app.secret_key = 'jsc_secreta_2026_seguranca_maxima'

banco_dados.init_db()

SERVIDOR_NUVEM_URL = "https://svc.jscsaude.com.br"

# ==============================================================================
# SINCRONIZAÇÃO AUTOMÁTICA NA INICIALIZAÇÃO (PULL DA NUVEM)
# ==============================================================================
def sincronizar_ao_iniciar():
    """Baixa automaticamente usuários e dados da nuvem assim que o app abre"""
    if not SERVIDOR_NUVEM_URL:
        return
    try:
        req_pull = urllib.request.Request(f"{SERVIDOR_NUVEM_URL}/api/sync/enviar_tudo", method="GET")
        with urllib.request.urlopen(req_pull, timeout=8) as res_pull:
            dados_nuvem = json.loads(res_pull.read().decode('utf-8'))
            banco_dados.mesclar_dados_recebidos(dados_nuvem)
            print("Sincronizacao automatica inicial realizada com sucesso!")
    except Exception as e:
        print("Modo offline: Nao foi possivel conectar ao servidor na inicializacao.", str(e))

# ==============================================================================
# SISTEMA DE SEGURANÇA E LOGIN
# ==============================================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_logado' not in session or not isinstance(session['usuario_logado'], dict):
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_user = request.form.get('login')
        senha_user = request.form.get('senha')
        
        usuario = banco_dados.validar_login(login_user, senha_user)
        if usuario:
            session['usuario_logado'] = usuario
            return redirect(url_for('index'))
        else:
            return render_template('login.html', erro="Usuário ou senha inválidos.")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==============================================================================
# ROTAS PROTEGIDAS DO SISTEMA
# ==============================================================================
@app.route('/')
@login_required
def index():
    if session['usuario_logado']['permissao'] == 'consulta':
        return redirect(url_for('historico'))
    return render_template('index.html')

@app.route('/diagrama')
@login_required
def diagrama():
    return render_template('diagrama.html')

@app.route('/historico')
@login_required
def historico():
    return render_template('historico.html')

@app.route('/usuarios')
@login_required
def usuarios():
    if session['usuario_logado']['permissao'] != 'adm':
        return redirect(url_for('historico'))
    return render_template('usuarios.html')

@app.route('/api/usuarios', methods=['GET'])
@login_required
def get_usuarios():
    if session['usuario_logado']['permissao'] != 'adm':
        return jsonify({"error": "Acesso negado."}), 403
    return jsonify(banco_dados.listar_usuarios())

@app.route('/api/usuarios', methods=['POST'])
@login_required
def add_usuario():
    if session['usuario_logado']['permissao'] != 'adm':
        return jsonify({"error": "Acesso negado."}), 403
    data = request.json
    sucesso, msg = banco_dados.criar_usuario(data['nome'], data['login'], data['permissao'])
    if sucesso:
        return jsonify({"message": msg})
    return jsonify({"error": msg}), 400

@app.route('/api/usuarios', methods=['DELETE'])
@login_required
def delete_usuario():
    if session['usuario_logado']['permissao'] != 'adm':
        return jsonify({"error": "Acesso negado."}), 403
    data = request.json
    if data['id'] == session['usuario_logado']['id']:
        return jsonify({"error": "Você não pode excluir seu próprio usuário."}), 400
    banco_dados.excluir_usuario(data['id'])
    return jsonify({"message": "Usuário excluído!"})

@app.route('/upload', methods=['POST'])
@app.route('/api/upload', methods=['POST'])
@app.route('/importar', methods=['POST'])
@login_required
def upload_file():
    if session['usuario_logado']['permissao'] == 'consulta':
        return jsonify({"error": "Acesso negado para o seu perfil."}), 403
    try:
        if len(request.files) == 0: return jsonify({"error": "Nenhum arquivo"}), 400
        file_key = list(request.files.keys())[0]
        file = request.files[file_key]
        lote = request.form.get('lote', 'Sem Nome')
        svc = request.form.get('svc', 'SVC1')
        
        if file.filename == '': return jsonify({"error": "Arquivo vazio"}), 400
        if file.filename.lower().endswith('.txt'): df = pd.read_csv(file, sep='\t', encoding='latin1')
        elif file.filename.lower().endswith(('.xls', '.xlsx')): df = pd.read_excel(file)
        else: return jsonify({"error": "Formato não suportado."}), 400

        banco_dados.salvar_planilha_sql(df, lote, svc)
        return jsonify({"message": f"Arquivo importado com sucesso!"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Erro: {str(e)}"}), 500

@app.route('/api/lotes', methods=['GET'])
@login_required
def get_lotes():
    return jsonify(banco_dados.listar_lotes_salvos())

@app.route('/api/diagrama_dados', methods=['GET'])
@login_required
def get_diagrama_dados():
    svc = request.args.get('svc')
    lote = request.args.get('lote')
    harmonica = request.args.get('harmonica')
    if not all([svc, lote, harmonica]): return jsonify({"error": "Faltam parâmetros"}), 400
    return jsonify(banco_dados.buscar_dados_diagrama(lote, svc, harmonica))

@app.route('/api/troca', methods=['POST'])
@login_required
def realizar_troca():
    if session['usuario_logado']['permissao'] == 'consulta':
        return jsonify({"error": "O perfil de Consulta não pode realizar alterações."}), 403
    data = request.json
    try:
        banco_dados.efetivar_troca(data['lote'], data['svc'], data['harmonica'], data['cap1'], data['cap2'])
        return jsonify({"message": "Troca realizada!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/historico', methods=['GET'])
@login_required
def get_historico():
    return jsonify(banco_dados.listar_historico())

@app.route('/api/lotes', methods=['DELETE'])
@login_required
def delete_lote():
    if session['usuario_logado']['permissao'] != 'adm':
        return jsonify({"error": "Apenas administradores podem excluir medições."}), 403
    data = request.json
    try:
        banco_dados.excluir_lote(data['lote'], data['svc'])
        return jsonify({"message": "Excluído com sucesso!"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/lote/dados_completos', methods=['GET'])
@login_required
def get_dados_completos():
    return jsonify(banco_dados.buscar_dados_brutos(request.args.get('lote'), request.args.get('svc')))

@app.route('/api/lote/logs_trocas', methods=['GET'])
@login_required
def get_logs_trocas():
    return jsonify(banco_dados.buscar_logs_troca(request.args.get('lote'), request.args.get('svc')))

# ==============================================================================
# ENDPOINTS DE SINCRONIZAÇÃO
# ==============================================================================
@app.route('/api/sync/executar', methods=['POST'])
@login_required
def executar_sincronizacao():
    if not SERVIDOR_NUVEM_URL: return jsonify({"error": "URL não configurada."}), 400
    try:
        dados_locais = banco_dados.obter_dados_nao_sincronizados()
        ids_med = [m['id'] for m in dados_locais['medicoes']]
        ids_trc = [t['id'] for t in dados_locais['trocas']]
        ids_usr = [u['id'] for u in dados_locais['usuarios']]

        if ids_med or ids_trc or ids_usr:
            req = urllib.request.Request(f"{SERVIDOR_NUVEM_URL}/api/sync/receber", method="POST")
            req.add_header('Content-Type', 'application/json')
            dados_bytes = json.dumps(dados_locais).encode('utf-8')
            with urllib.request.urlopen(req, data=dados_bytes, timeout=15) as res:
                if res.status == 200:
                    banco_dados.marcar_como_sincronizados(ids_med, ids_trc, ids_usr)

        req_pull = urllib.request.Request(f"{SERVIDOR_NUVEM_URL}/api/sync/enviar_tudo", method="GET")
        with urllib.request.urlopen(req_pull, timeout=15) as res_pull:
            dados_nuvem = json.loads(res_pull.read().decode('utf-8'))
            
        banco_dados.mesclar_dados_recebidos(dados_nuvem)
        return jsonify({"message": "Sincronizado com sucesso!"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Falha na comunicação: {str(e)}"}), 500

@app.route('/api/sync/receber', methods=['POST'])
def receber_da_borda():
    try:
        banco_dados.mesclar_dados_recebidos(request.json)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sync/enviar_tudo', methods=['GET'])
def enviar_para_borda():
    return jsonify(banco_dados.obter_todos_dados_nuvem())

@app.route('/debug/contar')
def debug_contar():
    conn = sqlite3.connect(banco_dados.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM medicoes")
    total = cursor.fetchone()[0]
    conn.close()
    return f"Total de linhas no banco '{banco_dados.DB_NAME}': {total}"

# ==============================================================================
# INICIALIZAÇÃO COM JANELA NATIVA E ENCERRAMENTO AUTOMÁTICO
# ==============================================================================
if __name__ == '__main__':
    # 1. Executa a sincronização automática silenciosa na abertura
    sincronizar_ao_iniciar()

    # 2. Sobe o servidor Flask em uma thread de fundo
    def run_flask():
        app.run(debug=False, port=5000, host='127.0.0.1', use_reloader=False)

    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # 3. Abre a janela nativa do aplicativo. Ao clicar no 'X', o Python morre e limpa a memória.
    webview.create_window("Analise SVC - Sistema Local", "http://127.0.0.1:5000", width=1280, height=800)
    webview.start()
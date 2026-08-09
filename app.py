from flask import Flask, render_template, request, jsonify
import pandas as pd
import banco_dados
import traceback
import urllib.request
import json

app = Flask(__name__)
banco_dados.init_db()

# ==============================================================================
# CONFIGURAÇÃO DE SINCRONIZAÇÃO EDGE-TO-CLOUD
# Se for rodar no Notebook, digite o IP ou Domínio do seu Ubuntu Server abaixo.
# Se for rodar no Ubuntu Server, deixe vazio ("").
# ==============================================================================
SERVIDOR_NUVEM_URL = "https://svc.jscsaude.com.br"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/diagrama')
def diagrama():
    return render_template('diagrama.html')

@app.route('/historico')
def historico():
    return render_template('historico.html')

@app.route('/upload', methods=['POST'])
@app.route('/api/upload', methods=['POST'])
@app.route('/importar', methods=['POST'])
def upload_file():
    try:
        if len(request.files) == 0:
            return jsonify({"error": "Nenhum arquivo recebido pelo backend"}), 400
            
        file_key = list(request.files.keys())[0]
        file = request.files[file_key]
        lote = request.form.get('lote', 'Sem Nome')
        svc = request.form.get('svc', 'SVC1')
        
        if file.filename == '':
            return jsonify({"error": "Arquivo vazio"}), 400

        if file.filename.lower().endswith('.txt'):
            df = pd.read_csv(file, sep='\t', encoding='latin1')
        elif file.filename.lower().endswith(('.xls', '.xlsx')):
             df = pd.read_excel(file)
        else:
            return jsonify({"error": "Formato não suportado."}), 400

        banco_dados.salvar_planilha_sql(df, lote, svc)
        return jsonify({"message": f"Arquivo importado com sucesso para o Banco SQL!"})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

@app.route('/api/lotes', methods=['GET'])
def get_lotes():
    return jsonify(banco_dados.listar_lotes_salvos())

@app.route('/api/diagrama_dados', methods=['GET'])
def get_diagrama_dados():
    svc = request.args.get('svc')
    lote = request.args.get('lote')
    harmonica = request.args.get('harmonica')
    if not all([svc, lote, harmonica]): return jsonify({"error": "Faltam parâmetros"}), 400
    return jsonify(banco_dados.buscar_dados_diagrama(lote, svc, harmonica))

@app.route('/api/troca', methods=['POST'])
def realizar_troca():
    data = request.json
    try:
        banco_dados.efetivar_troca(data['lote'], data['svc'], data['harmonica'], data['cap1'], data['cap2'])
        return jsonify({"message": "Troca realizada!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def get_historico():
    return jsonify(banco_dados.listar_historico())

@app.route('/api/lotes', methods=['DELETE'])
def delete_lote():
    data = request.json
    try:
        banco_dados.excluir_lote(data['lote'], data['svc'])
        return jsonify({"message": "Excluído com sucesso!"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/lote/dados_completos', methods=['GET'])
def get_dados_completos():
    return jsonify(banco_dados.buscar_dados_brutos(request.args.get('lote'), request.args.get('svc')))

@app.route('/api/lote/logs_trocas', methods=['GET'])
def get_logs_trocas():
    return jsonify(banco_dados.buscar_logs_troca(request.args.get('lote'), request.args.get('svc')))

# ==============================================================================
# ENDPOINTS DE SINCRONIZAÇÃO
# ==============================================================================

@app.route('/api/sync/executar', methods=['POST'])
def executar_sincronizacao():
    """Botão do Frontend do Notebook chama esta rota para comandar a sincronização"""
    if not SERVIDOR_NUVEM_URL:
        return jsonify({"error": "A URL do Servidor Nuvem não foi configurada no arquivo app.py do notebook."}), 400

    try:
        # 1. Pega tudo que foi feito no notebook e ainda não subiu
        dados_locais = banco_dados.obter_dados_nao_sincronizados()
        ids_med = [m['id'] for m in dados_locais['medicoes']]
        ids_trc = [t['id'] for t in dados_locais['trocas']]

        # 2. Envia para o Servidor Ubuntu (Push)
        if ids_med or ids_trc:
            req = urllib.request.Request(f"{SERVIDOR_NUVEM_URL}/api/sync/receber", method="POST")
            req.add_header('Content-Type', 'application/json')
            dados_bytes = json.dumps(dados_locais).encode('utf-8')
            with urllib.request.urlopen(req, data=dados_bytes, timeout=15) as res:
                if res.status == 200:
                    # 3. Se o Ubuntu confirmou recebimento, marca como sincronizado no notebook
                    banco_dados.marcar_como_sincronizados(ids_med, ids_trc)

        # 4. Pede para o Servidor Ubuntu mandar todos os dados dele para o notebook (Pull)
        req_pull = urllib.request.Request(f"{SERVIDOR_NUVEM_URL}/api/sync/enviar_tudo", method="GET")
        with urllib.request.urlopen(req_pull, timeout=15) as res_pull:
            dados_nuvem = json.loads(res_pull.read().decode('utf-8'))
            
        # 5. Salva os dados no banco local do notebook
        banco_dados.mesclar_dados_recebidos(dados_nuvem)

        return jsonify({"message": "Notebook sincronizado com sucesso com o servidor Ubuntu!"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Falha na comunicação com o servidor: {str(e)}"}), 500

@app.route('/api/sync/receber', methods=['POST'])
def receber_da_borda():
    """Apenas o Servidor Ubuntu recebe chamadas aqui para salvar os dados dos notebooks"""
    try:
        banco_dados.mesclar_dados_recebidos(request.json)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sync/enviar_tudo', methods=['GET'])
def enviar_para_borda():
    """Apenas o Servidor Ubuntu recebe chamadas aqui para exportar seu banco para os notebooks"""
    return jsonify(banco_dados.obter_todos_dados_nuvem())

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
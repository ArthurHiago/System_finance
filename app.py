import streamlit as st
import pandas as pd
import pyodbc # <-- Substituiu o sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
from datetime import datetime
from cerebro_nlp import CerebroFinanceiro
import warnings

# Oculta avisos chatos do Pandas usando a conexão do pyodbc
warnings.filterwarnings('ignore', category=UserWarning)

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Finanças Pro", page_icon="💎", layout="wide")

def aplicar_estilo():
    st.markdown("""
        <style>
        .stApp { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); color: white; }
        div[data-testid="metric-container"] {
            background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border-radius: 15px; padding: 15px; border: 1px solid rgba(255,255,255,0.1);
        }
        .stButton > button {
            background: linear-gradient(90deg, #6c5ce7, #a29bfe); color: white; border: none; border-radius: 20px;
        }
        .stProgress > div > div > div > div { background-color: #00cec9; }
        </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM A NUVEM AZURE ---
def get_conexao_azure():
    # Puxamos tudo limpo do cofre
    driver = st.secrets['azure']['driver']
    server = st.secrets['azure']['server']
    db = st.secrets['azure']['database']
    user = st.secrets['azure']['username']
    pwd = st.secrets['azure']['password']
    
    # String oficial e direta da Microsoft
    conn_str = f"DRIVER={driver};SERVER=tcp:{server},1433;DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
    
    return pyodbc.connect(conn_str)

# --- BANCO DE DADOS NA NUVEM ---
def inicializar_banco():
    conn = get_conexao_azure()
    cursor = conn.cursor()
    
    # Função auxiliar para criar as tabelas no Azure sem erro
    def criar_tabela(nome, colunas):
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{nome}' AND xtype='U') CREATE TABLE {nome} ({colunas})")
    
    # Criando as tabelas com a sintaxe do SQL Server
    criar_tabela("users", "id INT PRIMARY KEY IDENTITY(1,1), username NVARCHAR(100) UNIQUE, password NVARCHAR(MAX)")
    criar_tabela("categorias", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), meta_mensal FLOAT, user_id INT")
    criar_tabela("transacoes", "id INT PRIMARY KEY IDENTITY(1,1), valor FLOAT, loja NVARCHAR(255), data_compra DATE, banco_origem NVARCHAR(100), tipo NVARCHAR(50), categoria_id INT, user_id INT")
    criar_tabela("investimentos", "id INT PRIMARY KEY IDENTITY(1,1), ativo NVARCHAR(100), tipo NVARCHAR(50), valor_investido FLOAT, data_aplicacao DATE, user_id INT")
    criar_tabela("notificacoes_historico", "id INT PRIMARY KEY IDENTITY(1,1), data_recebimento DATE, titulo NVARCHAR(255), mensagem NVARCHAR(MAX), status_ia NVARCHAR(50), user_id INT")
    criar_tabela("sonhos", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), custo FLOAT, salvo FLOAT, user_id INT")
    criar_tabela("contas_fixas", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), valor FLOAT, dia_vencimento INT, user_id INT")
    
    conn.commit()
    conn.close()

# --- SEGURANÇA BLINDADA ---
def verificar_login(u, p):
    conn = get_conexao_azure()
    cursor = conn.cursor()
    r = cursor.execute("SELECT id, password FROM users WHERE username=?", (u,)).fetchone()
    conn.close()
    if r and check_password_hash(r[1], p):
        return r[0] # Retorna o ID
    return None

def criar_usuario(u, p):
    conn = get_conexao_azure()
    cursor = conn.cursor()
    try: 
        hash_seguro = generate_password_hash(p)
        cursor.execute("INSERT INTO users (username, password) VALUES (?,?)", (u, hash_seguro))
        conn.commit()
        return True
    except: 
        return False
    finally: 
        conn.close()

# --- TELAS ---
def tela_login():
    st.markdown("<h1 style='text-align: center; color: #a29bfe;'>Finanças Pro 💎</h1>", unsafe_allow_html=True)
    
    conn = get_conexao_azure()
    cursor = conn.cursor()
    # Verifica se a tabela users existe e se tem usuários
    try:
        tem_usuario = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0
    except:
        tem_usuario = False
    conn.close()

    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        if not tem_usuario:
            st.warning("⚠️ Modo de Instalação: Crie o usuário Administrador para travar o sistema na Nuvem.")
            with st.form("c"):
                u = st.text_input("Novo Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Criar Conta e Blindar"): 
                    if criar_usuario(u,p): 
                        st.success("Conta criada no Azure! O sistema agora está trancado. Recarregue a página (F5).")
        else:
            with st.form("l"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    uid = verificar_login(u, p)
                    if uid: 
                        st.session_state.user_id=uid
                        st.session_state.username=u
                        st.session_state.logged_in=True
                        st.rerun()
                    else: st.error("Credenciais inválidas ou senha incorreta.")

def app_principal():
    uid = st.session_state.user_id
    aplicar_estilo()
    cerebro = CerebroFinanceiro()

    with st.sidebar:
        st.write(f"👤 **{st.session_state.username}**")
        
        if "renda" not in st.session_state: st.session_state.renda = 3000.0
        st.session_state.renda = st.number_input("Renda Mensal", value=st.session_state.renda)
        
        if st.button("Sair"): st.session_state.logged_in=False; st.rerun()
        st.divider()
        if st.button("🔄 Puxar do Celular"):
            msg = cerebro.sincronizar_notificacoes_nuvem(uid)
            st.success(msg)

        st.markdown("### 📅 Período")
        meses = {1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr", 5:"Mai", 6:"Jun", 7:"Jul", 8:"Ago", 9:"Set", 10:"Out", 11:"Nov", 12:"Dez"}
        c_m, c_a = st.columns(2)
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        
        mes_sel = c_m.selectbox("Mês", list(meses.values()), index=mes_atual-1, label_visibility="collapsed")
        ano_sel = c_a.number_input("Ano", value=ano_atual, step=1, label_visibility="collapsed")
        
        mes_num = list(meses.keys())[list(meses.values()).index(mes_sel)]
        mes_str = f"{mes_num:02d}"
        ano_str = str(ano_sel)

        st.divider()
        
        st.markdown("### 🎮 Pote dos Sonhos")
        conn = get_conexao_azure()
        cursor = conn.cursor()
        sonhos = cursor.execute("SELECT id, nome, custo, salvo FROM sonhos WHERE user_id=?", (uid,)).fetchall()
        
        if sonhos:
            for sid, nome, custo, salvo in sonhos:
                custo_float = float(custo) if custo else 1.0
                salvo_float = float(salvo) if salvo else 0.0
                progresso = min(salvo_float / custo_float, 1.0) if custo_float > 0 else 0.0
                progresso = max(0.0, progresso) 
                
                st.write(f"**{nome}** (R$ {salvo_float:.0f} / R$ {custo_float:.0f})")
                st.progress(progresso)
        st.divider()
        
        if "chat" not in st.session_state: st.session_state.chat = []
        if "ctx" not in st.session_state: st.session_state.ctx = None
        
        p = st.chat_input("Fale com a IA...")
        if p:
            st.session_state.chat.append({"role":"user", "msg":p})
            if st.session_state.ctx:
                resp, extra = cerebro.processar_comando(p, uid, st.session_state.ctx)
                st.session_state.ctx = None
            else:
                resp, extra = cerebro.processar_comando(p, uid)
                if isinstance(extra, dict) and extra.get("status") == "PENDENTE_TIPO":
                    st.session_state.ctx = extra.get("dados_temp")
            st.session_state.chat.append({"role":"assistant", "msg":resp})
            st.rerun()
        
        with st.container(height=200):
            for m in st.session_state.chat: st.write(f"**{'Você' if m['role']=='user' else 'IA'}**: {m['msg']}")

    abas = st.tabs(["🔮 Oráculo & Geral", "📅 Agenda Fixa", "🕵️ Assinaturas", "📝 Manual", "🎮 Sonhos", "📈 Investimentos", "🧠 Treino"])
    
    # 1. ORÁCULO E GERAL
    with abas[0]:
        analise = cerebro.analisar_oraculo(uid, st.session_state.renda)
        
        c_oraculo, c_chart = st.columns([1, 2])
        with c_oraculo:
            st.markdown(f"### 🔮 O Oráculo (Atual)")
            st.metric("Saldo Previsto", f"R$ {analise['saldo_final']:.2f}", analise['status'])
            st.info(analise['msg'])
            
            renda_segura = max(st.session_state.renda, 1.0)
            st.progress(min(analise['gasto_atual'] / renda_segura, 1.0))
            st.caption(f"Gasto Atual: R$ {analise['gasto_atual']:.2f}")

        with c_chart:
            # Atenção: O Azure usa MONTH() e YEAR() em vez do strftime do SQLite
            query = "SELECT * FROM transacoes WHERE user_id=? AND MONTH(data_compra)=? AND YEAR(data_compra)=?"
            df = pd.read_sql_query(query, conn, params=(uid, mes_num, int(ano_str)))
            
            st.metric(f"Gasto em {mes_sel}/{ano_sel}", f"R$ {df['valor'].sum():.2f}" if not df.empty else "R$ 0,00")
            
            if not df.empty:
                st.markdown("#### Fluxo Diário")
                df['data'] = pd.to_datetime(df['data_compra'])
                st.area_chart(df.groupby(df['data'].dt.day)['valor'].sum(), color="#6c5ce7")

        st.divider()
        st.markdown(f"### 📝 Histórico de Compras ({mes_sel}/{ano_sel})")
        if not df.empty:
            df_hist = df[['data_compra', 'loja', 'valor', 'tipo']].copy()
            df_hist.rename(columns={'data_compra': 'Data', 'loja': 'Loja', 'valor': 'Valor (R$)', 'tipo': 'Tipo'}, inplace=True)
            st.dataframe(df_hist.sort_values(by='Data', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma transação encontrada para o período selecionado.")

    # 2. AGENDA DE CONTAS FIXAS
    with abas[1]:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("#### ➕ Nova Conta Fixa")
            with st.form("add_bill"):
                nome = st.text_input("Nome (ex: Aluguel)")
                val = st.number_input("Valor", min_value=1.0)
                dia = st.number_input("Dia Vencimento", 1, 31)
                if st.form_submit_button("Agendar"):
                    cerebro.adicionar_conta_fixa(nome, val, dia, uid)
                    st.success("Agendado!")
                    st.rerun()
        
        with c2:
            st.markdown("#### 📅 Próximos Vencimentos")
            alertas, total_prox = cerebro.verificar_contas_proximas(uid)
            if alertas:
                for a in alertas: st.warning(a)
            else:
                st.success("Sem contas vencendo nos próximos 7 dias.")
            
            contas = pd.read_sql_query("SELECT id, nome, valor, dia_vencimento FROM contas_fixas WHERE user_id=?", conn, params=(uid,))
            st.dataframe(contas, hide_index=True)
            
            ids = contas['id'].tolist()
            if ids:
                del_id = st.selectbox("Remover Conta ID", ids)
                if st.button("Apagar Conta"):
                    cerebro.remover_conta_fixa(del_id)
                    st.rerun()

    # 3. DETETIVE DE ASSINATURAS
    with abas[2]:
        st.subheader("🕵️ Detetive de Recorrência")
        assinaturas = cerebro.detectar_assinaturas(uid)
        
        if assinaturas:
            for item in assinaturas:
                st.markdown(f"""
                <div style="background:rgba(255,255,255,0.05); padding:15px; border-left:5px solid #00cec9; margin-bottom:10px;">
                    <h4>{item['loja']} (R$ {item['valor']:.2f})</h4>
                    <p>{item['msg']}</p>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Nenhuma assinatura suspeita detectada ainda (preciso de 2 meses de dados).")

    # 4. MANUAL
    with abas[3]:
        with st.form("smart"):
            c1, c2 = st.columns(2)
            l = c1.text_input("Loja")
            val_sug = 0.0
            if l:
                v_mem, n_mem = cerebro.obter_ultimo_valor(l, uid)
                if v_mem > 0: val_sug = v_mem
            v = c2.number_input("Valor", value=val_sug)
            t = st.selectbox("Tipo", ["Débito", "Crédito", "Pix"])
            if st.form_submit_button("Lançar"):
                m, _ = cerebro._acao_registrar_gasto(v, l, datetime.now().strftime('%Y-%m-%d'), uid, tipo=t)
                st.success(m); st.rerun()

    # 5. SONHOS
    with abas[4]:
        c1, c2 = st.columns(2)
        with c1:
            with st.form("n_dream"):
                n = st.text_input("Sonho")
                c = st.number_input("Custo", min_value=1.0) 
                if st.form_submit_button("Criar"): 
                    cerebro.criar_sonho(n, c, uid); st.rerun()
        with c2:
            s_db = cursor.execute("SELECT id, nome FROM sonhos WHERE user_id=?", (uid,)).fetchall()
            if s_db:
                with st.form("save"):
                    sid = st.selectbox("Sonho", s_db, format_func=lambda x:x[1])
                    v = st.number_input("Guardar", min_value=0.01) 
                    if st.form_submit_button("Depositar"): 
                        cerebro.processar_poupanca_sonho(sid[0], v); st.rerun()

    # 6. INVESTIMENTOS
    with abas[5]:
        with st.form("inv"):
            c1, c2, c3 = st.columns(3)
            a = c1.text_input("Ativo"); v = c2.number_input("Valor"); t = c3.selectbox("Tipo", ["Ação", "FII", "Renda Fixa"])
            if st.form_submit_button("Investir"):
                cursor.execute("INSERT INTO investimentos (ativo, tipo, valor_investido, data_aplicacao, user_id) VALUES (?,?,?,?,?)", (a,t,v,datetime.now().strftime('%Y-%m-%d'), uid))
                conn.commit(); st.success("Salvo!"); st.rerun()
        dfi = pd.read_sql_query("SELECT * FROM investimentos WHERE user_id=?", conn, params=(uid,))
        st.dataframe(dfi)

    # 7. TREINO
    with abas[6]:
        lojas = [r[0] for r in cursor.execute("SELECT DISTINCT loja FROM transacoes WHERE user_id=?", (uid,)).fetchall()]
        if lojas:
            c1, c2 = st.columns(2)
            l_sel = c1.selectbox("Loja", lojas)
            n_cat = c2.text_input("Categoria Correta")
            if st.button("Corrigir"):
                st.success(cerebro._acao_treinar_notificacao(l_sel, n_cat, uid))
    
    conn.close()

# --- RUN ---
inicializar_banco()
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in: tela_login()
else: app_principal()
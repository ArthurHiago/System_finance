import streamlit as st
import pandas as pd
import pyodbc
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
from datetime import datetime
from cerebro_nlp import CerebroFinanceiro
import warnings
import smtplib
from email.mime.text import MIMEText

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
    driver = st.secrets['azure']['driver']
    server = st.secrets['azure']['server']
    db = st.secrets['azure']['database']
    user = st.secrets['azure']['username']
    pwd = st.secrets['azure']['password']
    
    conn_str = f"DRIVER={driver};SERVER=tcp:{server},1433;DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
    return pyodbc.connect(conn_str)

# --- BANCO DE DADOS NA NUVEM ---
def inicializar_banco():
    conn = get_conexao_azure()
    cursor = conn.cursor()
    
    def criar_tabela(nome, colunas):
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{nome}' AND xtype='U') CREATE TABLE {nome} ({colunas})")
    
    criar_tabela("users", "id INT PRIMARY KEY IDENTITY(1,1), username NVARCHAR(100) UNIQUE, password NVARCHAR(MAX)")
    criar_tabela("categorias", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), meta_mensal FLOAT, user_id INT")
    criar_tabela("transacoes", "id INT PRIMARY KEY IDENTITY(1,1), valor FLOAT, loja NVARCHAR(255), data_compra DATE, banco_origem NVARCHAR(100), tipo NVARCHAR(50), categoria_id INT, user_id INT")
    criar_tabela("investimentos", "id INT PRIMARY KEY IDENTITY(1,1), ativo NVARCHAR(100), tipo NVARCHAR(50), valor_investido FLOAT, data_aplicacao DATE, user_id INT")
    criar_tabela("notificacoes_historico", "id INT PRIMARY KEY IDENTITY(1,1), data_recebimento DATE, titulo NVARCHAR(255), mensagem NVARCHAR(MAX), status_ia NVARCHAR(50), user_id INT")
    criar_tabela("sonhos", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), custo FLOAT, salvo FLOAT, user_id INT")
    criar_tabela("contas_fixas", "id INT PRIMARY KEY IDENTITY(1,1), nome NVARCHAR(100), valor FLOAT, dia_vencimento INT, user_id INT")
    criar_tabela("perfil", "id INT PRIMARY KEY IDENTITY(1,1), emprego NVARCHAR(100), renda_mensal FLOAT, onboarding_concluido BIT DEFAULT 0, user_id INT")
    
    # NOVA TABELA PARA SALVAR OS BUGS NA NUVEM
    criar_tabela("bugs_reportados", "id INT PRIMARY KEY IDENTITY(1,1), descricao NVARCHAR(MAX), data_report DATE, user_id INT")
    
    conn.commit()
    conn.close()

# --- SEGURANÇA BLINDADA ---
def verificar_login(u, p):
    conn = get_conexao_azure()
    cursor = conn.cursor()
    r = cursor.execute("SELECT id, password FROM users WHERE username=?", (u,)).fetchone()
    conn.close()
    if r and check_password_hash(r[1], p):
        return r[0]
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
    
    aba_login, aba_cadastro = st.tabs(["🔑 Entrar", "📝 Criar Conta"])
    
    with aba_login:
        with st.form("form_login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                uid = verificar_login(u, p)
                if uid: 
                    st.session_state.user_id = uid
                    st.session_state.username = u
                    st.session_state.logged_in = True
                    st.rerun()
                else: 
                    st.error("Credenciais inválidas ou senha incorreta.")
                    
    with aba_cadastro:
        st.caption("Novo por aqui? Crie sua conta para isolar seus dados financeiros.")
        with st.form("form_cadastro"):
            novo_u = st.text_input("Escolha um Nome de Usuário")
            nova_p = st.text_input("Crie uma Senha", type="password")
            confirma_p = st.text_input("Confirme a Senha", type="password")
            
            if st.form_submit_button("Cadastrar e Blindar Conta", use_container_width=True):
                if nova_p != confirma_p:
                    st.error("⚠️ As senhas não coincidem!")
                elif len(novo_u) < 3 or len(nova_p) < 4:
                    st.error("⚠️ O usuário deve ter pelo menos 3 letras e a senha 4 caracteres.")
                else:
                    conn = get_conexao_azure()
                    cursor = conn.cursor()
                    existe = cursor.execute("SELECT id FROM users WHERE username=?", (novo_u,)).fetchone()
                    
                    if existe:
                        st.warning("⚠️ Esse nome de usuário já está em uso. Escolha outro.")
                    else:
                        if criar_usuario(novo_u, nova_p):
                            st.success("✅ Conta criada com sucesso no Azure! Volte na aba 'Entrar' para acessar o sistema.")
                        else:
                            st.error("❌ Erro ao criar conta no banco de dados.")
                    conn.close()
# --- ENVIO DE E-MAIL ---
def enviar_email_bug(descricao, usuario_nome):
    try:
        # Pega as credenciais de envio nos secrets
        remetente = st.secrets['email']['endereco']
        senha = st.secrets['email']['senha']
        destinatario = "arthur.silvino@estudantes.ifc.edu.br"
        
        corpo_email = f"O usuário '{usuario_nome}' reportou o seguinte bug:\n\n{descricao}"
        
        msg = MIMEText(corpo_email)
        msg['Subject'] = 'Bug Report - Finanças Pro'
        msg['From'] = remetente
        msg['To'] = destinatario

        # Conecta no servidor do Gmail e dispara
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        return False
def app_principal():
    uid = st.session_state.user_id
    aplicar_estilo()
    cerebro = CerebroFinanceiro()
    
    conn = get_conexao_azure()
    cursor = conn.cursor()

    # --- VERIFICAÇÃO DE ONBOARDING ---
    perfil = cursor.execute("SELECT emprego, renda_mensal, onboarding_concluido FROM perfil WHERE user_id=?", (uid,)).fetchone()
    
    if not perfil or perfil[2] == False:
        st.markdown("## 🚀 Bem-vindo ao Finanças Pro!")
        st.write("Vamos configurar seu perfil para que a inteligência do sistema funcione perfeitamente.")
        
        with st.form("form_onboarding"):
            c1, c2 = st.columns(2)
            emprego = c1.text_input("Profissão / Cargo", placeholder="Ex: Suporte Técnico")
            renda = c2.number_input("Qual seu salário/renda média mensal?", min_value=0.0, value=1500.0)
            
            st.markdown("#### 📅 Adicione suas principais contas fixas")
            st.caption("Você poderá adicionar outras depois.")
            
            col1, col2, col3 = st.columns(3)
            conta1 = col1.text_input("Conta 1 (Ex: Internet)", key="c1")
            val1 = col2.number_input("Valor", key="v1")
            dia1 = col3.number_input("Dia do Vencimento", 1, 31, key="d1")
            
            if st.form_submit_button("Concluir Configuração", use_container_width=True):
                if not perfil:
                    cursor.execute("INSERT INTO perfil (emprego, renda_mensal, onboarding_concluido, user_id) VALUES (?, ?, 1, ?)", (emprego, renda, uid))
                else:
                    cursor.execute("UPDATE perfil SET emprego=?, renda_mensal=?, onboarding_concluido=1 WHERE user_id=?", (emprego, renda, uid))
                
                if conta1 and val1 > 0:
                    cursor.execute("INSERT INTO contas_fixas (nome, valor, dia_vencimento, user_id) VALUES (?, ?, ?, ?)", (conta1, val1, dia1, uid))
                
                conn.commit()
                st.success("Tudo pronto! Carregando seu painel...")
                st.rerun()
                
        conn.close()
        st.stop()
    
    if "renda" not in st.session_state: 
        st.session_state.renda = perfil[1] if perfil else 0.0

    # --- COBRADOR INTELIGENTE ---
    hoje = datetime.now()
    contas_fixas = pd.read_sql_query("SELECT id, nome, valor, dia_vencimento FROM contas_fixas WHERE user_id=?", conn, params=(uid,))
    
    alertas_exibidos = 0
    for idx, row in contas_fixas.iterrows():
        if hoje.day >= row['dia_vencimento'] - 3:
            sql_pago = "SELECT id FROM transacoes WHERE user_id=? AND loja=? AND MONTH(data_compra)=? AND YEAR(data_compra)=?"
            ja_pago = cursor.execute(sql_pago, (uid, row['nome'], hoje.month, hoje.year)).fetchone()
            
            if not ja_pago:
                alertas_exibidos += 1
                with st.container():
                    st.markdown(f"""
                        <div style="background-color: rgba(255, 75, 75, 0.1); border: 1px solid #ff4b4b; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                            <h4 style="margin:0; color: #ff4b4b;">⚠️ Pagamento Pendente: {row['nome']}</h4>
                            <p style="margin:5px 0 0 0;">Valor: <b>R$ {row['valor']:.2f}</b> | Vencimento: dia {row['dia_vencimento']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c1, c2 = st.columns([1, 4])
                    if c1.button(f"💸 Já paguei", key=f"pagar_btn_{row['id']}"):
                        cerebro._acao_registrar_gasto(
                            valor=row['valor'], 
                            loja=row['nome'], 
                            data=hoje.strftime('%Y-%m-%d'), 
                            user_id=uid,
                            tipo="Pix"
                        )
                        st.success(f"Excelente! R$ {row['valor']:.2f} debitado do seu saldo mensal.")
                        st.rerun()
                        
    if alertas_exibidos > 0:
        st.divider()

    # --- SIDEBAR E MENU ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state.username}**")
        # A opção de alterar renda sumiu daqui e foi para a aba de Configurações!
        
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
        sonhos = cursor.execute("SELECT id, nome, custo, salvo FROM sonhos WHERE user_id=?", (uid,)).fetchall()
        
        if sonhos:
            for sid, nome, custo, salvo in sonhos:
                custo_float = float(custo) if custo else 1.0
                salvo_float = float(salvo) if salvo else 0.0
                progresso = min(salvo_float / custo_float, 1.0) if custo_float > 0 else 0.0
                st.write(f"**{nome}** (R$ {salvo_float:.0f} / R$ {custo_float:.0f})")
                st.progress(max(0.0, progresso))
        
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

    # --- ABAS PRINCIPAIS (Adicionada aba 8: Config & Ajuda) ---
    abas = st.tabs(["Geral", "📊 Planilha Interativa", "Contas Fixa", "Recorrencia", "📝 Manual", "🎮 Sonhos", "📈 Investimentos", "🧠 Treino", "⚙️ Config & Ajuda"])
    
    # 0. ORÁCULO E GERAL
    with abas[0]:
        analise = cerebro.analisar_oraculo(uid, st.session_state.renda)
        
        c_oraculo, c_chart = st.columns([1, 2])
        with c_oraculo:
            st.markdown(f"###  Atual")
            st.metric("Saldo Previsto", f"R$ {analise['saldo_final']:.2f}", analise['status'])
            
            if "ALERTA" in analise.get('alerta_vermelho', '') or "JÁ ESTÁ" in analise.get('alerta_vermelho', ''):
                st.error(analise.get('alerta_vermelho', ''))
            elif analise.get('alerta_vermelho'):
                st.success(analise.get('alerta_vermelho', ''))
                
            st.info(analise['msg'])
            
            renda_segura = max(st.session_state.renda, 1.0)
            st.progress(min(analise['gasto_atual'] / renda_segura, 1.0))
            st.caption(f"Gasto Atual: R$ {analise['gasto_atual']:.2f}")

        with c_chart:
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

    # 1. PLANILHA INTERATIVA
    with abas[1]:
        st.markdown("### 📊 Lançamento em Massa")
        st.caption("Preencha a planilha abaixo. Você pode adicionar novas linhas ao final da tabela.")
        
        df_base = pd.DataFrame(
            [{"Data": datetime.now().date(), "Loja": "", "Valor": 0.0, "Tipo": "Débito"}]
        )
        
        df_editado = st.data_editor(
            df_base,
            column_config={
                "Data": st.column_config.DateColumn("Data", required=True),
                "Loja": st.column_config.TextColumn("Loja / Descrição", required=True),
                "Valor": st.column_config.NumberColumn("Valor (R$)", min_value=0.0, format="R$ %.2f", required=True),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Débito", "Crédito", "Pix"], required=True)
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("💾 Salvar Planilha no Banco", use_container_width=True):
            salvos = 0
            for index, row in df_editado.iterrows():
                if pd.notna(row["Loja"]) and row["Loja"].strip() != "" and row["Valor"] > 0:
                    data_str = row["Data"].strftime('%Y-%m-%d')
                    cerebro._acao_registrar_gasto(
                        valor=row["Valor"],
                        loja=row["Loja"],
                        data=data_str,
                        user_id=uid,
                        tipo=row["Tipo"]
                    )
                    salvos += 1
                    
            if salvos > 0:
                st.success(f"✅ {salvos} transações salvas com sucesso no banco de dados!")
                st.rerun()
            else:
                st.warning("⚠️ Nenhuma transação válida para salvar. Preencha Loja e Valor nas linhas.")

    # 2. AGENDA DE CONTAS FIXAS
    with abas[2]:
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
            st.markdown("#### 📅 Contas Cadastradas")
            contas = pd.read_sql_query("SELECT id, nome, valor, dia_vencimento FROM contas_fixas WHERE user_id=?", conn, params=(uid,))
            st.dataframe(contas, hide_index=True)
            
            ids = contas['id'].tolist()
            if ids:
                del_id = st.selectbox("Remover Conta ID", ids)
                if st.button("Apagar Conta"):
                    cerebro.remover_conta_fixa(del_id)
                    st.rerun()

    # 3. DETETIVE DE ASSINATURAS
    with abas[3]:
        st.subheader("Recorrência")
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
    with abas[4]:
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
    with abas[5]:
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
    with abas[6]:
        with st.form("inv"):
            c1, c2, c3 = st.columns(3)
            a = c1.text_input("Ativo"); v = c2.number_input("Valor"); t = c3.selectbox("Tipo", ["Ação", "FII", "Renda Fixa"])
            if st.form_submit_button("Investir"):
                cursor.execute("INSERT INTO investimentos (ativo, tipo, valor_investido, data_aplicacao, user_id) VALUES (?,?,?,?,?)", (a,t,v,datetime.now().strftime('%Y-%m-%d'), uid))
                conn.commit(); st.success("Salvo!"); st.rerun()
        dfi = pd.read_sql_query("SELECT * FROM investimentos WHERE user_id=?", conn, params=(uid,))
        st.dataframe(dfi)

    # 7. TREINO
    with abas[7]:
        lojas = [r[0] for r in cursor.execute("SELECT DISTINCT loja FROM transacoes WHERE user_id=?", (uid,)).fetchall()]
        if lojas:
            c1, c2 = st.columns(2)
            l_sel = c1.selectbox("Loja", lojas)
            n_cat = c2.text_input("Categoria Correta")
            if st.button("Corrigir"):
                st.success(cerebro._acao_treinar_notificacao(l_sel, n_cat, uid))
                
    # 8. CONFIGURAÇÕES E AJUDA (NOVA ABA)
    with abas[8]:
        st.markdown("### ⚙️ Configurações da Conta")
        
        c_conf1, c_conf2 = st.columns(2)
        
        with c_conf1:
            st.markdown("#### Atualizar Renda Mensal")
            nova_renda = st.number_input("Sua nova renda (R$)", value=float(st.session_state.renda), min_value=0.0)
            if st.button("Salvar Renda"):
                cursor.execute("UPDATE perfil SET renda_mensal=? WHERE user_id=?", (nova_renda, uid))
                conn.commit()
                st.session_state.renda = nova_renda
                st.success("Renda atualizada no banco de dados!")
                
            st.markdown("#### Alterar Nome de Usuário")
            novo_nome = st.text_input("Novo Usuário", value=st.session_state.username)
            if st.button("Salvar Novo Nome"):
                existe = cursor.execute("SELECT id FROM users WHERE username=?", (novo_nome,)).fetchone()
                if existe and existe[0] != uid:
                    st.error("Nome de usuário já está em uso!")
                else:
                    cursor.execute("UPDATE users SET username=? WHERE id=?", (novo_nome, uid))
                    conn.commit()
                    st.session_state.username = novo_nome
                    st.success("Nome de usuário alterado com sucesso!")
                    
        with c_conf2:
            st.markdown("#### Alterar Senha")
            nova_senha = st.text_input("Nova Senha", type="password")
            confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
            if st.button("Salvar Nova Senha"):
                if nova_senha != confirma_senha:
                    st.error("As senhas não coincidem!")
                elif len(nova_senha) < 4:
                    st.error("A senha deve ter pelo menos 4 caracteres.")
                else:
                    hash_seguro = generate_password_hash(nova_senha)
                    cursor.execute("UPDATE users SET password=? WHERE id=?", (hash_seguro, uid))
                    conn.commit()
                    st.success("Senha alterada com segurança no Azure!")

        st.divider()
        
        st.markdown("### 🐛 Encontrou algum Bug?")
        st.caption("Relate problemas ou sugira melhorias. O relatório será enviado diretamente para o e-mail do desenvolvedor.")
        bug_txt = st.text_area("Descreva o que aconteceu:", placeholder="Ex: Ao tentar apagar uma conta fixa, a tela piscou e não apagou...")
        
        if st.button("Enviar Relatório de Bug"):
            if bug_txt.strip() != "":
                # 1. Salva no banco de dados como backup
                cursor.execute("INSERT INTO bugs_reportados (descricao, data_report, user_id) VALUES (?, ?, ?)", (bug_txt, datetime.now().strftime('%Y-%m-%d'), uid))
                conn.commit()
                
                # 2. Tenta enviar o e-mail
                enviou = enviar_email_bug(bug_txt, st.session_state.username)
                
                if enviou:
                    st.success("Relatório enviado por e-mail com sucesso! Muito obrigado por ajudar a melhorar o app.")
                else:
                    st.warning("O bug foi salvo no sistema, mas houve um erro ao tentar enviar o e-mail. Verifique as credenciais no servidor.")
            else:
                st.warning("Por favor, escreva alguma coisa antes de enviar.")
        st.divider()
        
        st.markdown("### 📖 Guia de Uso: Como funciona o Finanças Pro?")
        st.caption("Clique nas sessões abaixo para entender o que cada parte do aplicativo faz.")
        
        with st.expander("Geral"):
            st.write("É o coração do sistema. Ele calcula o seu ritmo atual de gastos diários e faz uma matemática avançada para prever **exatamente em qual dia** o seu dinheiro vai acabar. Ele cruza sua Renda Mensal com tudo que você já gastou.")
            
        with st.expander("📊 Planilha Interativa"):
            st.write("Um jeito rápido de adicionar várias compras de uma vez só (estilo Excel). Preencha as linhas clicando nos espaços em branco. Quando terminar, clique em salvar e todas as linhas vão de uma vez só para a nuvem.")
            
        with st.expander("📅 Agenda Fixa"):
            st.write("Cadastre suas contas que repetem todo mês (como Luz, Internet e Aluguel) e o dia que elas vencem. Quando a conta estiver a 3 dias do vencimento, o app vai te avisar com um botão rápido para registrar o pagamento.")
            
        with st.expander("🕵️ Assinaturas"):
            st.write("O sistema age como um detetive. Ele varre seu histórico dos últimos dois meses e acha compras com o mesmo nome e mesmo valor (como Netflix e Spotify), te avisando para onde seu dinheiro está vazando invisivelmente.")
            
        with st.expander("💬 Chat IA (Barra Lateral)"):
            st.write("Você pode falar com o app como se fosse o WhatsApp. Tente enviar mensagens como: *'Gastei 50 reais de gasolina na Shell'* ou *'Apague meu último gasto'*. Ele entende e salva automaticamente!, comandos limitados, então caso ele obtenha bugs mande para mim.")
    
    conn.close()

# --- RUN ---
inicializar_banco()
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in: tela_login()
else: app_principal()
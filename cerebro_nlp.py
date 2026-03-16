import re
import pyodbc
import calendar
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from thefuzz import process

class CerebroFinanceiro:
    def __init__(self):
        # Conhecimento Global
        self.conhecimento_global = {
            "uber": "Transporte", "99": "Transporte", "shell": "Transporte", "posto": "Transporte",
            "ifood": "Alimentação", "mcdonalds": "Alimentação", "bk": "Alimentação", "mercado": "Alimentação",
            "netflix": "Assinaturas", "spotify": "Assinaturas", "prime": "Assinaturas",
            "shopee": "Compras", "shein": "Compras", "amazon": "Compras",
            "farmacia": "Saúde", "drogasil": "Saúde",
            "steam": "Lazer", "playstation": "Lazer", "xbox": "Lazer", "cinema": "Lazer",
            "aluguel": "Moradia", "luz": "Moradia", "internet": "Moradia", "condominio": "Moradia"
        }
        # Nota: As tabelas agora são iniciadas pelo app.py, centralizando a criação no Azure.

    # --- CONEXÃO SEGURA COM AZURE ---
    # Adicione o 'self' aqui! 👇
    def get_conexao_azure(self):
        # Puxamos tudo limpo do cofre
        driver = st.secrets['azure']['driver']
        server = st.secrets['azure']['server']
        db = st.secrets['azure']['database']
        user = st.secrets['azure']['username']
        pwd = st.secrets['azure']['password']
        
        # String oficial e direta da Microsoft
        conn_str = f"DRIVER={driver};SERVER=tcp:{server},1433;DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
        
        return pyodbc.connect(conn_str)

    # --- 0. A PONTE COM O CELULAR (GOOGLE SHEETS) ---
    def sincronizar_notificacoes_nuvem(self, user_id):
        url_csv = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR8nFgJ3NDCoZMYL_yv8jVnwCe0w3FGX3-grjHe3AXUf1VlYwVgcKRB50CrvDuOSNDvwFKZB6pJiiYk/pub?output=csv"
        
        try:
            df = pd.read_csv(url_csv)
            if df.empty or len(df.columns) < 2:
                return "📭 Nenhuma notificação nova na nuvem."

            conn = self.get_conexao_azure()
            cursor = conn.cursor()
            novas = 0
            
            col_data = df.columns[0]
            col_texto = df.columns[1]

            for index, row in df.iterrows():
                data_hora_bruta = str(row[col_data])
                texto_bruto = str(row[col_texto])
                
                if "TESTE" in texto_bruto.upper() or texto_bruto == "nan":
                    continue

                # --- MÁGICA DA DATA PARA O AZURE ---
                try:
                    # O Pandas lê a data do Google (ex: 03/03/2026 14:30) e formata para YYYY-MM-DD
                    data_hora = pd.to_datetime(data_hora_bruta, dayfirst=True).strftime('%Y-%m-%d')
                except:
                    # Fallback de segurança: se vier uma data totalmente ilegível, usa a data de hoje
                    data_hora = datetime.now().strftime('%Y-%m-%d')

                ja_existe = cursor.execute("SELECT id FROM notificacoes_historico WHERE data_recebimento=? AND mensagem=?", (data_hora, texto_bruto)).fetchone()
                
                if not ja_existe:
                    msg_retorno, extra = self.processar_notificacao_raw("Celular", texto_bruto, user_id)
                    status = extra.get("status", "PROCESSADO")
                    
                    cursor.execute("INSERT INTO notificacoes_historico (data_recebimento, titulo, mensagem, status_ia, user_id) VALUES (?,?,?,?,?)",
                                 (data_hora, "Nuvem", texto_bruto, status, user_id))
                    
                    if status != "IGNORADO" and status != "ERRO":
                        novas += 1
            
            conn.commit(); conn.close()
            return f"🔄 Sincronização concluída! {novas} compras novas registradas." if novas > 0 else "✅ Tudo atualizado! Não há gastos novos."
        except Exception as e:
            return f"⚠️ Erro ao conectar com o Google ou Banco: {e}"

    # --- 1. O ORÁCULO (PREVISÃO) ---
    def analisar_oraculo(self, user_id, renda_mensal):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        hoje = datetime.now()
        dia_atual = hoje.day
        ultimo_dia_mes = calendar.monthrange(hoje.year, hoje.month)[1]
        
        # Azure usa MONTH() para extrair o mês da data
        sql = "SELECT SUM(valor) FROM transacoes WHERE user_id=? AND MONTH(data_compra)=?"
        res = cursor.execute(sql, (user_id, hoje.month)).fetchone()
        gasto_atual = res[0] if res[0] else 0
        conn.close()

        media_diaria = gasto_atual / max(1, dia_atual)
        dias_restantes = ultimo_dia_mes - dia_atual
        projecao_gasto = gasto_atual + (media_diaria * dias_restantes)
        saldo_projetado = renda_mensal - projecao_gasto
        
        status = "🟢 Positivo" if saldo_projetado > 0 else "🔴 Negativo"
        msg = f"Nesse ritmo, você gastará **R$ {projecao_gasto:.2f}**. Saldo final: **R$ {saldo_projetado:.2f}**."
        
        return {"gasto_atual": gasto_atual, "projecao": projecao_gasto, "saldo_final": saldo_projetado, "msg": msg, "status": status}

    # --- 2. AGENDA DE CONTAS FIXAS ---
    def adicionar_conta_fixa(self, nome, valor, dia, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO contas_fixas (nome, valor, dia_vencimento, user_id) VALUES (?, ?, ?, ?)", (nome, valor, dia, user_id))
        conn.commit(); conn.close()
        return f"📅 {nome} agendado para todo dia {dia}!"

    def remover_conta_fixa(self, id_conta):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contas_fixas WHERE id=?", (id_conta,))
        conn.commit(); conn.close()
        return "🗑️ Conta removida."

    def verificar_contas_proximas(self, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        contas = cursor.execute("SELECT nome, valor, dia_vencimento FROM contas_fixas WHERE user_id=?", (user_id,)).fetchall()
        conn.close()
        
        hoje = datetime.now().day
        alertas = []
        total_a_pagar = 0
        
        for nome, valor, dia in contas:
            if hoje <= dia <= (hoje + 7):
                dias_para_vencer = dia - hoje
                msg_dia = "hoje!" if dias_para_vencer == 0 else f"em {dias_para_vencer} dias."
                alertas.append(f"⚠️ **{nome}** (R$ {valor:.2f}) vence {msg_dia}")
                total_a_pagar += valor
                
        return alertas, total_a_pagar

    # --- 3. DETETIVE DE ASSINATURAS ---
    def detectar_assinaturas(self, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        data_limite = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        sql = """
            SELECT loja, valor, COUNT(*) as qtd 
            FROM transacoes 
            WHERE user_id=? AND data_compra >= ? 
            GROUP BY loja, valor 
            HAVING COUNT(*) >= 2
        """
        recorrentes = cursor.execute(sql, (user_id, data_limite)).fetchall()
        conn.close()
        
        lista_detectada = []
        for loja, valor, qtd in recorrentes:
            if valor < 500: 
                lista_detectada.append({"loja": loja, "valor": valor, "msg": f"Pagou {loja} {qtd} vezes recentemente."})
        
        return lista_detectada

    # --- 4. TRATAMENTO DE NOTIFICAÇÕES (RAW) ---
    def processar_notificacao_raw(self, titulo, mensagem, user_id):
        texto = f"{titulo} {mensagem}".lower()
        bloqueados = ["oferta", "conferir", "limite", "disponível", "empréstimo", "fatura fechada", "convide"]
        for b in bloqueados:
            if b in texto: return f"🚫 Ignorado: {b}", {"status": "IGNORADO"}
        
        match_val = re.search(r"(?:r\$|rs|\$)\s*(\d+[.,]?\d*)", texto)
        if not match_val: 
            if "compra" in texto: match_val = re.search(r"(\d+[.,]\d{2})", texto)
        
        if not match_val: return "⚠️ Sem valor.", {"status": "ERRO"}
        
        try:
            val_str = match_val.group(1).replace('.', '').replace(',', '.')
            if "." not in val_str and "," in match_val.group(1): val_str = match_val.group(1).replace(',', '.')
            valor = float(val_str)
        except: return "⚠️ Erro valor.", {"status": "ERRO"}

        loja = "Desconhecido"
        match_loja = re.search(r"(em|no|na|para)\s+(.*?)(?=\s+R\$|\s+valor|\s+via|\.|,|!|$)", texto, re.IGNORECASE)
        if match_loja: loja = match_loja.group(2).strip().title()
        elif "ifood" in texto: loja = "Ifood"
        elif "uber" in texto: loja = "Uber"
        else: loja = titulo

        tipo = "Débito"
        if "crédito" in texto or "credito" in texto: tipo = "Crédito"
        elif "pix" in texto: tipo = "Pix"

        return self._acao_registrar_gasto(valor, loja, datetime.now().strftime('%Y-%m-%d'), user_id, tipo=tipo)

    # --- 5. NLP - PROCESSAMENTO DE COMANDOS (CHAT) ---
    def processar_comando(self, texto, user_id, contexto_pendente=None):
        texto_raw = texto
        texto = texto.lower().strip().replace('?', '')
        
        if ":" in texto or "nubank" in texto or "empréstimo" in texto or "aprovada" in texto or ("compra" in texto and "r$" in texto):
            return self.processar_notificacao_raw("Chat", texto_raw, user_id)
            
        if contexto_pendente:
            tipo = "Débito"
            if "credito" in texto or "crédito" in texto: tipo = "Crédito"
            elif "pix" in texto: tipo = "Pix"
            d = contexto_pendente
            return self._acao_registrar_gasto(d['val'], d['loja'], d['data'], user_id, tipo=tipo, parcelas=d.get('parc', 1))

        if texto.startswith("mude ") or texto.startswith("altere "):
            return self._acao_corrigir_ultimo(texto, user_id)
            
        if any(x in texto for x in ["desfazer", "desfaça", "apague", "apagar", "cancele"]):
            return self._acao_desfazer_ultimo(user_id)

        if "quanto" in texto: 
            return self._acao_consulta(user_id, texto)

        padrao = r"(gastei|compra|paguei|pagar).*\s(\d+[.,]?\d*)\s*(reais|conto)?\s*(no|na|em|de|do|da|para|ao|à)?\s+(.+?)(?=\s+(ontem|hoje|dia\s+\d+|cat|categoria|em\s+\d+x)|$)"
        match = re.search(padrao, texto)
        if match:
            try:
                valor = float(match.group(2).replace(',', '.'))
                loja = match.group(5).strip().title() 
                data = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d') if "ontem" in texto else datetime.now().strftime('%Y-%m-%d')
                
                parcelas = 1
                match_p = re.search(r"(\d+)\s*x", texto)
                if match_p: parcelas = int(match_p.group(1))
                
                tipo = None
                if "credito" in texto or "crédito" in texto or parcelas > 1: tipo = "Crédito"
                elif "pix" in texto: tipo = "Pix"
                elif "debito" in texto or "débito" in texto: tipo = "Débito"
                
                if not tipo:
                    return f"💳 R$ {valor} na {loja}. **Crédito**, **Débito** ou **Pix**?", {"status": "PENDENTE_TIPO", "dados_temp": {"val": valor, "loja": loja, "data": data, "parc": parcelas}}
                
                return self._acao_registrar_gasto(valor, loja, data, user_id, tipo=tipo, parcelas=parcelas)
            except Exception as e: return f"Erro: {e}", {}
            
        return "🤔 Não entendi.", {}

    # --- 6. FUNÇÕES INTERNAS DE BANCO DE DADOS ---
    
    def _acao_desfazer_ultimo(self, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        # SQL Server usa TOP 1 em vez de LIMIT 1
        res = cursor.execute("SELECT TOP 1 id, loja, valor FROM transacoes WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchone()
        if not res:
            conn.close()
            return "Nada para desfazer.", {}
        cursor.execute("DELETE FROM transacoes WHERE id=?", (res[0],))
        conn.commit(); conn.close()
        return f"🗑️ Desfeito! Apaguei a transação de R$ {res[2]:.2f} em {res[1]}.", {}

    def _acao_corrigir_ultimo(self, texto, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        ultimo = cursor.execute("SELECT TOP 1 id, loja, valor FROM transacoes WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchone()
        if not ultimo:
            conn.close()
            return "Nenhuma transação recente para corrigir.", {}

        tid, loja_antiga, valor_antigo = ultimo
        
        if "valor" in texto:
            match = re.search(r"para\s+(\d+[.,]?\d*)", texto)
            if match:
                novo_val = float(match.group(1).replace(',', '.'))
                cursor.execute("UPDATE transacoes SET valor=? WHERE id=?", (novo_val, tid))
                conn.commit(); conn.close()
                return f"✏️ Corrigido! Valor de {loja_antiga} atualizado para R$ {novo_val:.2f}.", {}
                
        if "loja" in texto or "nome" in texto:
            match = re.search(r"para\s+(.+)", texto)
            if match:
                nova_loja = match.group(1).strip().title()
                cursor.execute("UPDATE transacoes SET loja=? WHERE id=?", (nova_loja, tid))
                conn.commit(); conn.close()
                return f"✏️ Corrigido! Loja atualizada para {nova_loja}.", {}
                
        conn.close()
        return "Não entendi a correção. Diga 'Mude o valor para 50' ou 'Mude a loja para Uber'.", {}

    def _acao_consulta(self, user_id, texto):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        mes_atual = datetime.now().month
        
        match_loja = re.search(r"(no|na|em)\s+([a-zA-Z0-9_]+)", texto)
        if match_loja and "mês" not in texto and "mes" not in texto:
            loja = match_loja.group(2).strip().title()
            res = cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id=? AND loja LIKE ?", (user_id, f"%{loja}%")).fetchone()
            tot = res[0] if res[0] else 0
            conn.close()
            return f"🔎 Total gasto em **{loja}**: R$ {tot:.2f}", {}
        
        res = cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id=? AND MONTH(data_compra)=?", (user_id, mes_atual)).fetchone()
        tot = res[0] if res[0] else 0
        conn.close()
        return f"📅 Total deste mês (Lançamentos e Parcelas): R$ {tot:.2f}", {}

    def _acao_registrar_gasto(self, valor, loja, data, user_id, cat_forcada=None, tipo="Débito", parcelas=1):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cat_id = None
        for k, v in self.conhecimento_global.items():
            if k in loja.lower():
                r = cursor.execute("SELECT id FROM categorias WHERE nome=? AND user_id=?", (v, user_id)).fetchone()
                if not r: 
                    cursor.execute("INSERT INTO categorias (nome, meta_mensal, user_id) VALUES (?, 1000, ?)", (v, user_id))
                cat_id = cursor.execute("SELECT id FROM categorias WHERE nome=? AND user_id=?", (v, user_id)).fetchone()[0]
                break
        if not cat_id:
            r = cursor.execute("SELECT id FROM categorias WHERE nome='Outros' AND user_id=?", (user_id,)).fetchone()
            if r:
                cat_id = r[0]
            else:
                cursor.execute("INSERT INTO categorias (nome, meta_mensal, user_id) VALUES ('Outros', 1000, ?)", (user_id,))
                # SQL Server usa @@IDENTITY para pegar o ultimo ID gerado
                cat_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        val_p = valor / parcelas
        for i in range(parcelas):
            dt = (datetime.strptime(data, '%Y-%m-%d') + relativedelta(months=i)).strftime('%Y-%m-%d')
            desc = f"{loja} ({i+1}/{parcelas})" if parcelas > 1 else loja
            cursor.execute("INSERT INTO transacoes (valor, loja, data_compra, tipo, user_id, categoria_id) VALUES (?,?,?,?,?,?)", (val_p, desc, dt, tipo, user_id, cat_id))
        conn.commit(); conn.close()
        return f"✅ R$ {valor:.2f} em {loja}", {}

    def obter_ultimo_valor(self, loja_parcial, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        lojas = [r[0] for r in cursor.execute("SELECT DISTINCT loja FROM transacoes WHERE user_id=?", (user_id,)).fetchall()]
        match = process.extractOne(loja_parcial, lojas) if lojas else None
        valor, nome = 0.0, ""
        if match and match[1] >= 70:
            nome = match[0]
            res = cursor.execute("SELECT TOP 1 valor FROM transacoes WHERE loja=? AND user_id=? ORDER BY id DESC", (nome, user_id)).fetchone()
            if res: valor = res[0]
        conn.close()
        return valor, nome

    def criar_sonho(self, nome, custo, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sonhos (nome, custo, salvo, user_id) VALUES (?, ?, 0, ?)", (nome, custo, user_id))
        conn.commit(); conn.close()

    def processar_poupanca_sonho(self, id_sonho, valor):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cursor.execute("UPDATE sonhos SET salvo = salvo + ? WHERE id = ?", (valor, id_sonho))
        conn.commit(); conn.close()

    def gerar_conselhos(self, user_id):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        dicas = []
        mes_atual = datetime.now().month
        
        # Heatmap (DATEPART do Azure substitui o strftime %w)
        sql = "SELECT TOP 1 DATEPART(dw, data_compra) as dia, SUM(valor) FROM transacoes WHERE user_id=? AND MONTH(data_compra)=? GROUP BY DATEPART(dw, data_compra) ORDER BY SUM(valor) DESC"
        res = cursor.execute(sql, (user_id, mes_atual)).fetchone()
        if res: dicas.append({"titulo": "📅 Dia de Pico", "msg": "Cuidado com esse dia da semana!", "cor": "orange", "icone": "🔥"})
        
        conn.close()
        return dicas

    def _acao_treinar_notificacao(self, l, c, u):
        conn = self.get_conexao_azure()
        cursor = conn.cursor()
        cid = cursor.execute("SELECT id FROM categorias WHERE nome=? AND user_id=?", (c, u)).fetchone()
        if not cid: 
            cursor.execute("INSERT INTO categorias (nome, meta_mensal, user_id) VALUES (?, 1000, ?)", (c, u))
            cid = cursor.execute("SELECT @@IDENTITY").fetchone()
        cursor.execute("UPDATE transacoes SET categoria_id=? WHERE loja LIKE ? AND user_id=?", (cid[0], f"%{l}%", u))
        conn.commit(); conn.close()
        return "Aprendido!"
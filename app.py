import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# --- Configuração da Página ---
st.set_page_config(page_title="Sagrado Doce - Sistema", layout="wide", page_icon="🍰")

# --- 1. CONEXÃO DIRETA (Segura, sem cache de conexão para evitar quedas) ---
def get_db_connection():
    try:
        db_url = st.secrets["SUPABASE_URL"]
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        st.stop()

# --- 2. CACHE APENAS PARA LEITURA (Acelera o carregamento das tabelas) ---
# TTL=300 significa que ele guarda os dados por 5 minutos antes de baixar de novo
@st.cache_data(ttl=300)
def carregar_dados(query):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        try:
            cur.execute(query)
            return cur.fetchall()
        except Exception:
            return []
    conn.close()

# --- 3. FUNÇÃO DE SALVAR (SEM CACHE - Para garantir que salva sem erro) ---
def salvar_no_banco(query, params=None):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        try:
            cur.execute(query, params)
            conn.commit()
            
            # Limpa o cache de leitura para que a nova info apareça na hora
            st.cache_data.clear()
            
            if "RETURNING id" in query.lower():
                return cur.fetchone()['id']
        except Exception as e:
            conn.rollback()
            st.error(f"Erro ao salvar: {e}")
    conn.close()

# --- Inicialização ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Tabelas
    c.execute('''CREATE TABLE IF NOT EXISTS insumos (id SERIAL PRIMARY KEY, nome TEXT, unidade_medida TEXT, custo_total REAL, qtd_embalagem REAL, fator_conversao REAL, custo_unitario REAL, estoque_atual REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS receitas (id SERIAL PRIMARY KEY, nome TEXT, preco_venda REAL, custo_total REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS receita_itens (id SERIAL PRIMARY KEY, receita_id INTEGER, insumo_id INTEGER, qtd_usada REAL, custo_item REAL, FOREIGN KEY(receita_id) REFERENCES receitas(id), FOREIGN KEY(insumo_id) REFERENCES insumos(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS vendas (id SERIAL PRIMARY KEY, cliente TEXT, data_pedido TIMESTAMP, tipo_entrega TEXT, endereco TEXT, forma_pagamento TEXT, itens_resumo TEXT, total_venda REAL, status TEXT, status_pagamento TEXT DEFAULT 'Pendente')''')
    c.execute('''CREATE TABLE IF NOT EXISTS venda_itens (id SERIAL PRIMARY KEY, venda_id INTEGER, receita_id INTEGER, qtd INTEGER, FOREIGN KEY(venda_id) REFERENCES vendas(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS caixa (id SERIAL PRIMARY KEY, descricao TEXT, valor REAL, data_movimento TIMESTAMP, tipo TEXT, categoria TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orcamentos (id SERIAL PRIMARY KEY, cliente TEXT, data_emissao TEXT, validade TEXT, total REAL, itens_resumo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vendedoras (id SERIAL PRIMARY KEY, nome TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS consignacoes (id SERIAL PRIMARY KEY, vendedora_id INTEGER, receita_id INTEGER, qtd_entregue REAL, qtd_vendida REAL DEFAULT 0, data_entrega TIMESTAMP, FOREIGN KEY(vendedora_id) REFERENCES vendedoras(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    conn.commit()
    conn.close()

if 'db_initialized' not in st.session_state:
    init_db(); st.session_state.db_initialized = True

# --- Funções Visuais ---
def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode()
    return None

def format_currency(value): return f"R$ {value:,.2f}"
def limpar_sessao(keys): 
    for k in keys: 
        if k in st.session_state: del st.session_state[k]

# --- CSS ---
st.markdown("""
    <style>
    .invoice-box { max-width: 800px; margin: auto; padding: 30px; border: 1px solid #eee; box-shadow: 0 0 10px rgba(0, 0, 0, 0.15); font-size: 16px; line-height: 24px; font-family: 'Helvetica Neue', 'Helvetica', Arial, sans-serif; color: #555; background-color: #fff; }
    .header-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .logo-container { max-width: 150px; }
    .logo-img { width: 100%; height: auto; }
    .header-title { color: #d63384; font-size: 28px; font-weight: bold; text-align: right;}
    .table-custom { width: 100%; border-collapse: collapse; margin-top: 20px; }
    .table-custom th { background-color: #f8f9fa; color: #333; padding: 10px; text-align: left; border-bottom: 2px solid #ddd; }
    .table-custom td { padding: 10px; border-bottom: 1px solid #eee; }
    .total-row { font-size: 18px; font-weight: bold; color: #d63384; }
    .subtotal-row { font-size: 14px; color: #777; text-align: right; }
    </style>
""", unsafe_allow_html=True)

# --- APP ---
st.title("🍰 Sagrado Doce - Gestão")

tab1, tab2, tab_estoque, tab_orc, tab3, tab4, tab_caixa = st.tabs([
    "📦 Insumos", "📒 Receitas", "📊 Estoque", "📑 Orçamentos", "🛒 Vendas", "📋 Produção", "💰 Financeiro"
])

# ================= ABA 1: INSUMOS (COM FORMULÁRIO) =================
with tab1:
    st.header("Cadastro de Insumos")
    # O st.form impede que o site recarregue enquanto você digita
    with st.form("form_insumos", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nome_insumo = st.text_input("Nome")
            unidade_tipo = st.selectbox("Unidade Uso", ["g (Gramas)", "mL (Mililitros)", "un (Unidade)"])
        with col2:
            custo_embalagem = st.number_input("Custo Embalagem (R$)", min_value=0.0, format="%.2f")
            qtd_embalagem = st.number_input("Qtd Embalagem", min_value=0.0, format="%.2f")
            unidade_compra = st.selectbox("Unidade Compra", ["kg", "g", "L", "mL", "un"])
        
        # O botão fica dentro do form
        submitted = st.form_submit_button("💾 Salvar Insumo")
        
        if submitted:
            if nome_insumo and custo_embalagem and qtd_embalagem:
                qtd_total_base = qtd_embalagem * 1000 if unidade_compra in ["kg", "L"] else qtd_embalagem
                custo_unitario_calc = custo_embalagem / qtd_total_base
                # Convertendo para float explicitamente para evitar erros
                salvar_no_banco("INSERT INTO insumos (nome, unidade_medida, custo_total, qtd_embalagem, fator_conversao, custo_unitario, estoque_atual) VALUES (%s, %s, %s, %s, %s, %s, 0)",
                          (nome_insumo, unidade_tipo.split()[0], float(custo_embalagem), float(qtd_total_base), 1, float(custo_unitario_calc)))
                st.success("Salvo!")
                st.rerun()

    st.divider()
    with st.expander("🗑️ Excluir Insumo"):
        # Usa CARREGAR_DADOS (Cache) para ser rápido
        data = carregar_dados("SELECT id, nome FROM insumos ORDER BY nome")
        insumos_del = pd.DataFrame(data) if data else pd.DataFrame()
        if not insumos_del.empty:
            sel_del_ins = st.selectbox("Selecione para excluir:", insumos_del['nome'])
            if st.button("Excluir Insumo Selecionado"):
                id_del = insumos_del[insumos_del['nome'] == sel_del_ins]['id'].values[0]
                salvar_no_banco("DELETE FROM insumos WHERE id=%s", (int(id_del),))
                st.success("Excluído!"); st.rerun()

    data_view = carregar_dados("SELECT nome, unidade_medida, custo_unitario FROM insumos ORDER BY nome")
    if data_view: st.dataframe(pd.DataFrame(data_view), use_container_width=True)

# ================= ABA 2: RECEITAS =================
with tab2:
    st.header("Gerenciar Receitas")
    if 'ingredientes_temp' not in st.session_state: st.session_state.ingredientes_temp = []
    if 'editando_id' not in st.session_state: st.session_state.editando_id = None 
    
    data = carregar_dados("SELECT id, nome FROM receitas ORDER BY nome")
    receitas_existentes = pd.DataFrame(data) if data else pd.DataFrame()
    modo_receita = st.radio("Ação:", ["Nova (Do Zero)", "Clonar/Escalar", "Editar Existente"], horizontal=True)

    if modo_receita in ["Clonar/Escalar", "Editar Existente"] and not receitas_existentes.empty:
        c_sel1, c_sel2 = st.columns([3, 1])
        sel_receita_nome = c_sel1.selectbox("Selecione a Receita", receitas_existentes['nome'])
        if c_sel2.button("Carregar"):
            rec_id = receitas_existentes[receitas_existentes['nome'] == sel_receita_nome]['id'].values[0]
            rec_data = carregar_dados(f"SELECT * FROM receitas WHERE id = {rec_id}")[0]
            itens_data = carregar_dados(f"SELECT ri.insumo_id, i.nome, ri.qtd_usada, i.unidade_medida, i.custo_unitario FROM receita_itens ri JOIN insumos i ON ri.insumo_id = i.id WHERE ri.receita_id = {rec_id}")
            st.session_state.ingredientes_temp = []
            if itens_data:
                for item in itens_data:
                    st.session_state.ingredientes_temp.append({'id': item['insumo_id'], 'nome': item['nome'], 'qtd': item['qtd_usada'], 'unidade': item['unidade_medida'], 'custo': item['qtd_usada'] * item['custo_unitario'], 'custo_unitario': item['custo_unitario']})
            if modo_receita == "Editar Existente":
                st.session_state.editando_id = int(rec_id)
                st.session_state['rec_nome_in'] = rec_data['nome']; st.session_state['rec_venda_in'] = rec_data['preco_venda']
            else:
                st.session_state.editando_id = None 
                st.session_state['rec_nome_in'] = f"{rec_data['nome']} (Cópia)"; st.session_state['rec_venda_in'] = 0.0

    if modo_receita == "Nova (Do Zero)" and st.session_state.get('rec_nome_in') != "" and st.session_state.editando_id is not None:
         st.session_state.editando_id = None; st.session_state.ingredientes_temp = []
         limpar_sessao(['rec_nome_in', 'rec_venda_in'])

    c1, c2 = st.columns([1, 2])
    nome_receita = c1.text_input("Nome da Receita", key="rec_nome_in")
    preco_venda = c2.number_input("Preço Venda (R$)", min_value=0.0, key="rec_venda_in")

    data_ins = carregar_dados("SELECT id, nome, unidade_medida, custo_unitario FROM insumos ORDER BY nome")
    insumos_db = pd.DataFrame(data_ins) if data_ins else pd.DataFrame()
    if not insumos_db.empty:
        with st.container(border=True):
            ci1, ci2, ci3 = st.columns([2, 1, 1])
            insumo_sel = ci1.selectbox("Insumo", insumos_db['nome'], key="rec_ins_sel")
            dat = insumos_db[insumos_db['nome'] == insumo_sel].iloc[0]
            qtd_add = ci2.number_input(f"Qtd ({dat['unidade_medida']})", min_value=0.0, key="rec_qtd_add")
            if ci3.button("➕ Add"):
                if qtd_add > 0:
                    st.session_state.ingredientes_temp.append({
                        'id': int(dat['id']), 'nome': insumo_sel, 'qtd': float(qtd_add), 
                        'unidade': dat['unidade_medida'], 
                        'custo': float(qtd_add * dat['custo_unitario']), 
                        'custo_unitario': float(dat['custo_unitario'])
                    })
                    st.rerun()

    if st.session_state.ingredientes_temp:
        st.markdown("### Ingredientes")
        for idx, item in enumerate(st.session_state.ingredientes_temp):
            cc1, cc2, cc3, cc4 = st.columns([3, 2, 2, 1])
            cc1.text(item['nome']); cc2.text(f"{item['qtd']:.3f} {item['unidade']}"); cc3.text(f"R$ {item['custo']:.2f}")
            if cc4.button("🗑️", key=f"d_{idx}"): st.session_state.ingredientes_temp.pop(idx); st.rerun()

        custo_total = sum(i['custo'] for i in st.session_state.ingredientes_temp)
        st.info(f"💵 Custo Total: **{format_currency(custo_total)}**")
        
        col_act1, col_act2 = st.columns([2, 1])
        if col_act1.button("💾 SALVAR RECEITA", type="primary"):
            if not st.session_state.rec_nome_in: st.error("Nome vazio!"); st.stop()
            
            val_venda = float(st.session_state.rec_venda_in)
            val_custo = float(custo_total)

            if modo_receita == "Editar Existente" and st.session_state.editando_id:
                salvar_no_banco("UPDATE receitas SET nome=%s, preco_venda=%s, custo_total=%s WHERE id=%s", 
                          (st.session_state.rec_nome_in, val_venda, val_custo, st.session_state.editando_id))
                salvar_no_banco("DELETE FROM receita_itens WHERE receita_id=%s", (st.session_state.editando_id,))
                final_id = st.session_state.editando_id
            else:
                final_id = salvar_no_banco("INSERT INTO receitas (nome, preco_venda, custo_total) VALUES (%s, %s, %s) RETURNING id", 
                          (st.session_state.rec_nome_in, val_venda, val_custo))
            
            for item in st.session_state.ingredientes_temp:
                salvar_no_banco("INSERT INTO receita_itens (receita_id, insumo_id, qtd_usada, custo_item) VALUES (%s, %s, %s, %s)", 
                          (int(final_id), int(item['id']), float(item['qtd']), float(item['custo'])))
            
            st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
            limpar_sessao(['rec_nome_in', 'rec_venda_in', 'rec_qtd_add']); st.success("Salvo!"); st.rerun()
            
        if col_act2.button("Excluir Receita"):
             if st.session_state.editando_id:
                salvar_no_banco("DELETE FROM receitas WHERE id=%s", (st.session_state.editando_id,))
                salvar_no_banco("DELETE FROM receita_itens WHERE receita_id=%s", (st.session_state.editando_id,))
                st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
                limpar_sessao(['rec_nome_in', 'rec_venda_in'])
                st.success("Excluída!"); st.rerun()

# ================= ABA 3: ESTOQUE =================
with tab_estoque:
    st.header("Estoque")
    data = carregar_dados("SELECT id, nome, unidade_medida FROM insumos ORDER BY nome")
    insumos = pd.DataFrame(data) if data else pd.DataFrame()
    if not insumos.empty:
        with st.form("form_estoque"):
            c1, c2 = st.columns(2)
            sel = c1.selectbox("Insumo", insumos['nome'])
            qtd = c2.number_input("Qtd Adicionar (Negativo reduz)", step=1.0)
            if st.form_submit_button("Atualizar Estoque"):
                iid = insumos[insumos['nome'] == sel]['id'].values[0]
                salvar_no_banco("UPDATE insumos SET estoque_atual = estoque_atual + %s WHERE id = %s", (float(qtd), int(iid)))
                st.success("Ok!"); st.rerun()
                
    data_stk = carregar_dados("SELECT nome, estoque_atual, unidade_medida FROM insumos ORDER BY nome")
    if data_stk: st.dataframe(pd.DataFrame(data_stk), use_container_width=True)

# ================= ABA 4: ORÇAMENTOS =================
with tab_orc:
    st.header("Orçamentos")
    with st.form("form_orc_header"):
        c_o1, c_o2 = st.columns([2, 1])
        orc_cliente = c_o1.text_input("Cliente")
        orc_validade = c_o2.selectbox("Validade", ["7 dias", "15 dias", "30 dias"])
        st.form_submit_button("Atualizar Cabeçalho") # Apenas para não recarregar

    if 'carrinho_orc' not in st.session_state: st.session_state.carrinho_orc = []
    
    tipo_item = st.radio("Adicionar:", ["Receita Cadastrada", "Item Personalizado (Avulso)"], horizontal=True)
    
    if tipo_item == "Receita Cadastrada":
        data = carregar_dados("SELECT id, nome, preco_venda, custo_total FROM receitas ORDER BY nome")
        receitas_orc = pd.DataFrame(data) if data else pd.DataFrame()
        if not receitas_orc.empty:
            with st.form("form_orc_item"):
                co1, co2 = st.columns([3, 1])
                prod_orc = co1.selectbox("Produto", receitas_orc['nome'])
                qtd_orc = co2.number_input("Qtd", min_value=1, value=1)
                if st.form_submit_button("Adicionar"):
                    d_orc = receitas_orc[receitas_orc['nome'] == prod_orc].iloc[0]
                    st.session_state.carrinho_orc.append({
                        'produto': prod_orc, 'qtd': float(qtd_orc), 
                        'unitario': float(d_orc['preco_venda']), 'custo_unit': float(d_orc['custo_total']), 
                        'total': float(qtd_orc * d_orc['preco_venda'])
                    })
                    st.rerun()
    else:
        with st.form("form_orc_avulso"):
            ca1, ca2, ca3 = st.columns(3)
            nome_avulso = ca1.text_input("Descrição do Item")
            custo_avulso = ca2.number_input("Custo Interno (R$)", min_value=0.0)
            preco_avulso = ca3.number_input("Preço de Venda (R$)", min_value=0.0)
            if st.form_submit_button("Add Avulso"):
                if nome_avulso and preco_avulso:
                    st.session_state.carrinho_orc.append({
                        'produto': nome_avulso, 'qtd': 1.0, 
                        'unitario': float(preco_avulso), 'custo_unit': float(custo_avulso), 
                        'total': float(preco_avulso)
                    })
                    st.rerun()
                
    if st.session_state.carrinho_orc:
        st.divider()
        df_orc = pd.DataFrame(st.session_state.carrinho_orc)
        df_orc['Lucro Est.'] = df_orc['total'] - (df_orc['custo_unit'] * df_orc['qtd'])
        st.dataframe(df_orc[['produto', 'qtd', 'unitario', 'total', 'Lucro Est.']], use_container_width=True)
        
        total_original = df_orc['total'].sum()
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            valor_final_desejado = st.number_input("Valor Final com Desconto (R$)", value=float(total_original), step=1.0)
            desconto_reais = total_original - valor_final_desejado
            desconto_perc = (desconto_reais / total_original) * 100 if total_original > 0 else 0
        with col_t2:
            st.metric("Total Final", format_currency(valor_final_desejado))

        if st.button("Limpar Orçamento"): st.session_state.carrinho_orc = []; st.rerun()
        
        if st.button("📄 Gerar Folha"):
            hoje = datetime.now().strftime("%d/%m/%Y")
            img_b64 = get_base64_image("logo.png") 
            logo_html = f'<div class="logo-container"><img src="data:image/png;base64,{img_b64}" class="logo-img"></div>' if img_b64 else '<div class="logo-container" style="font-size:40px">🍰</div>'
            itens_html = "".join([f"<tr><td>{i['produto']}</td><td>{i['qtd']}</td><td>{format_currency(i['unitario'])}</td><td>{format_currency(i['total'])}</td></tr>" for i in st.session_state.carrinho_orc])
            footer_table = f"""<tr class="total-row"><td colspan="3" style="text-align: right;">Total:</td><td>{format_currency(total_original)}</td></tr>"""
            if desconto_reais > 0:
                footer_table = f"""<tr><td colspan="3" class="subtotal-row">Subtotal:</td><td style="text-align: right;">{format_currency(total_original)}</td></tr><tr><td colspan="3" class="subtotal-row" style="color: red;">Desconto ({desconto_perc:.1f}%):</td><td style="text-align: right; color: red;">- {format_currency(desconto_reais)}</td></tr><tr class="total-row"><td colspan="3" style="text-align: right;">Total Final:</td><td>{format_currency(valor_final_desejado)}</td></tr>"""
            html = f"""<div class="invoice-box"><div class="header-top">{logo_html}<div class="header-title">Sagrado Doce</div></div><div style="margin:20px 0"><strong>Cliente:</strong> {orc_cliente}<br><strong>Data:</strong> {hoje}<br><strong>Validade:</strong> {orc_validade}</div><table class="table-custom"><tr class="heading"><th>Item</th><th>Qtd</th><th>Unit.</th><th>Total</th></tr>{itens_html}{footer_table}</table><div style="margin-top:40px; text-align:center; font-size:12px; color:#aaa;">Obrigado pela preferência!</div></div>"""
            st.markdown(html, unsafe_allow_html=True)

# ================= ABA 5: VENDAS (COM FORM) =================
with tab3:
    st.header("Vendas & Saídas")
    sub_tab_balcao, sub_tab_vendedoras = st.tabs(["🛒 Venda Balcão", "👜 Vendedoras / Consignado"])
    
    with sub_tab_balcao:
        with st.form("form_venda_balcao"):
            c1, c2 = st.columns(2)
            cli = c1.text_input("Cliente")
            tipo = c1.radio("Tipo", ["Retirada", "Entrega"], horizontal=True)
            pagto = c2.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"])
            end = c2.text_input("Endereço")
            st.divider()
            
            data = carregar_dados("SELECT id, nome, preco_venda FROM receitas ORDER BY nome")
            receitas = pd.DataFrame(data) if data else pd.DataFrame()
            if not receitas.empty:
                cc1, cc2 = st.columns([3, 1])
                prod = cc1.selectbox("Produto", receitas['nome'])
                qv = cc2.number_input("Qtd", min_value=1, value=1)
                
                add_carrinho = st.form_submit_button("Adicionar ao Carrinho")
                if add_carrinho:
                    if 'carrinho' not in st.session_state: st.session_state.carrinho = []
                    d_prod = receitas[receitas['nome'] == prod].iloc[0]
                    st.session_state.carrinho.append({
                        'id': int(d_prod['id']), 'produto': prod, 'qtd': float(qv), 
                        'total': float(qv * d_prod['preco_venda'])
                    })
                    st.success("Adicionado!")
                    st.rerun()

        if 'carrinho' in st.session_state and st.session_state.carrinho:
            df_c = pd.DataFrame(st.session_state.carrinho)
            st.dataframe(df_c[['qtd', 'produto', 'total']], use_container_width=True)
            tot = df_c['total'].sum()
            st.metric("Total", format_currency(tot))
            if st.button("✅ Confirmar Pedido", type="primary"):
                resumo = "; ".join([f"{x['qtd']}x {x['produto']}" for x in st.session_state.carrinho])
                vid = salvar_no_banco("INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (%s, NOW(), %s, %s, %s, %s, %s, 'Em Produção', 'Pendente') RETURNING id", 
                          (cli, tipo, end, pagto, resumo, float(tot)))
                for i in st.session_state.carrinho: 
                    salvar_no_banco("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (%s, %s, %s)", (vid, int(i['id']), int(i['qtd'])))
                st.session_state.carrinho = []; st.success("Venda Realizada!"); st.rerun()
            if st.button("Limpar"): st.session_state.carrinho = []; st.rerun()

    with sub_tab_vendedoras:
        c_v1, c_v2 = st.columns([1, 2])
        with c_v1:
            with st.form("cad_vendedora"):
                novo_nome_vend = st.text_input("Nova Vendedora")
                if st.form_submit_button("Cadastrar"):
                    salvar_no_banco("INSERT INTO vendedoras (nome) VALUES (%s)", (novo_nome_vend,))
                    st.success("Cadastrada!"); st.rerun()
            
            data_vend = carregar_dados("SELECT * FROM vendedoras ORDER BY nome")
            vendedoras_db = pd.DataFrame(data_vend) if data_vend else pd.DataFrame()
            if not vendedoras_db.empty:
                vendedora_sel_nome = st.selectbox("Selecionar Vendedora", vendedoras_db['nome'])
                vendedora_id = vendedoras_db[vendedoras_db['nome'] == vendedora_sel_nome]['id'].values[0]
                
                with st.form("sacola_entregar"):
                    st.write("Entregar Produto:")
                    if not receitas.empty:
                        prod_entregar = st.selectbox("Produto", receitas['nome'])
                        qtd_entregar = st.number_input("Qtd", min_value=1)
                        if st.form_submit_button("Entregar"):
                            id_prod_entregar = receitas[receitas['nome'] == prod_entregar]['id'].values[0]
                            salvar_no_banco("INSERT INTO consignacoes (vendedora_id, receita_id, qtd_entregue, data_entrega) VALUES (%s, %s, %s, NOW())", 
                                         (int(vendedora_id), int(id_prod_entregar), float(qtd_entregar)))
                            st.success("Entregue!"); st.rerun()

        with c_v2:
            if not vendedoras_db.empty:
                st.subheader(f"Sacola: {vendedora_sel_nome}")
                # Aqui usamos cache para ficar rapido a visualização
                data_sc = carregar_dados(f"SELECT c.id, r.nome, c.qtd_entregue, c.qtd_vendida, (c.qtd_entregue - c.qtd_vendida) as em_maos, r.preco_venda, r.id as rec_id FROM consignacoes c JOIN receitas r ON c.receita_id = r.id WHERE c.vendedora_id = {vendedora_id} AND (c.qtd_entregue - c.qtd_vendida) > 0")
                sacola = pd.DataFrame(data_sc) if data_sc else pd.DataFrame()
                if not sacola.empty:
                    st.dataframe(sacola[['nome', 'qtd_entregue', 'qtd_vendida', 'em_maos']], use_container_width=True)
                    st.divider()
                    
                    with st.form("baixa_form"):
                        st.markdown("#### Registrar Venda (Baixa)")
                        cb1, cb2 = st.columns(2)
                        item_baixa = cb1.selectbox("Produto vendido?", sacola['nome'] + " (ID: " + sacola['id'].astype(str) + ")")
                        qtd_venda_vend = cb1.number_input("Qtd Vendida", min_value=1)
                        pagto_vend = cb1.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"])
                        receber_agora = cb1.checkbox("Já recebi o dinheiro", value=True)
                        desconto_un = cb2.number_input("Desconto UNITÁRIO (R$)", min_value=0.0)
                        
                        if st.form_submit_button("✅ Registrar Venda"):
                            id_consignacao = int(item_baixa.split("ID: ")[1].replace(")", ""))
                            dados_item = sacola[sacola['id'] == id_consignacao].iloc[0]
                            
                            if qtd_venda_vend > dados_item['em_maos']: st.error("Qtd maior que estoque da vendedora!")
                            else:
                                salvar_no_banco("UPDATE consignacoes SET qtd_vendida = qtd_vendida + %s WHERE id = %s", (float(qtd_venda_vend), id_consignacao))
                                total_v = (float(dados_item['preco_venda']) - float(desconto_un)) * float(qtd_venda_vend)
                                resumo = f"{qtd_venda_vend}x {dados_item['nome']} (Via {vendedora_sel_nome})"
                                st_pg = 'Pago' if receber_agora else 'Pendente'
                                vid = salvar_no_banco("INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (%s, NOW(), 'Venda Externa', %s, %s, %s, %s, 'Concluído', %s) RETURNING id", 
                                          (f"Vend. {vendedora_sel_nome}", "N/A", pagto_vend, resumo, float(total_v), st_pg))
                                salvar_no_banco("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (%s, %s, %s)", (vid, int(dados_item['rec_id']), int(qtd_venda_vend)))
                                if receber_agora: salvar_no_banco("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), 'Entrada', 'Vendas')", (f"Venda #{vid} - {vendedora_sel_nome}", float(total_v)))
                                st.success("Venda Registrada!"); st.rerun()

# ================= ABA 6: PRODUÇÃO =================
with tab4:
    st.header("Produção")
    st_filtro = st.radio("Ver", ["Em Produção", "Concluídos"], horizontal=True)
    st_db = "Em Produção" if st_filtro == "Em Produção" else "Concluído"
    data = carregar_dados(f"SELECT * FROM vendas WHERE status = '{st_db}' ORDER BY id DESC")
    df = pd.DataFrame(data) if data else pd.DataFrame()
    if not df.empty:
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**#{r['id']} {r['cliente']}**"); c1.text(r['itens_resumo'])
                status_pag = "🔴 Pendente" if r['status_pagamento'] == "Pendente" else "🟢 Pago"
                c2.text(f"{r['tipo_entrega']} | {r['forma_pagamento']}"); c2.markdown(f"**{status_pag}**")
                if r['status'] == "Em Produção":
                    if c3.button("Finalizar Produção", key=f"f_{r['id']}"):
                        salvar_no_banco("UPDATE vendas SET status='Concluído' WHERE id=%s", (r['id'],)); st.rerun()
                with c3.expander("Opções"):
                     if st.button("🗑️ Excluir Pedido", key=f"del_v_{r['id']}"):
                         salvar_no_banco("DELETE FROM vendas WHERE id=%s", (r['id'],)); salvar_no_banco("DELETE FROM venda_itens WHERE venda_id=%s", (r['id'],)); st.warning("Excluído"); st.rerun()

# ================= ABA 7: CAIXA =================
with tab_caixa:
    st.header("Financeiro")
    data_p = carregar_dados("SELECT id, cliente, total_venda FROM vendas WHERE status_pagamento = 'Pendente'")
    pend = pd.DataFrame(data_p) if data_p else pd.DataFrame()
    if not pend.empty:
        st.subheader("A Receber")
        for _, r in pend.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"#{r['id']} {r['cliente']} - {format_currency(r['total_venda'])}")
                if c2.button("Receber", key=f"rec_{r['id']}"):
                    salvar_no_banco("UPDATE vendas SET status_pagamento='Pago' WHERE id=%s", (r['id'],))
                    salvar_no_banco("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), 'Entrada', 'Vendas')", (f"Venda #{r['id']}", float(r['total_venda'])))
                    st.rerun()
    
    st.divider()
    with st.expander("Lançamento Manual"):
        with st.form("form_cx_manual"):
            l1, l2, l3 = st.columns(3)
            tp = l1.radio("Tipo", ["Saída", "Entrada"]); desc = l2.text_input("Desc"); val = l2.number_input("Valor")
            cat = l3.selectbox("Cat", ["Contas", "Insumos", "Outros"])
            if st.form_submit_button("Lançar"): 
                salvar_no_banco("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), %s, %s)", (desc, float(val), tp, cat)); st.rerun()
    
    data_cx = carregar_dados("SELECT * FROM caixa ORDER BY id DESC LIMIT 50")
    cx = pd.DataFrame(data_cx) if data_cx else pd.DataFrame()
    if not cx.empty:
        ent = cx[cx['tipo']=='Entrada']['valor'].sum(); sai = cx[cx['tipo']=='Saída']['valor'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", format_currency(ent)); c2.metric("Saídas", format_currency(sai)); c3.metric("Saldo", format_currency(ent-sai))
        st.dataframe(cx, use_container_width=True)

with st.sidebar:
    if st.button("Atualizar Dados (Limpar Cache)"): st.cache_data.clear(); st.rerun()

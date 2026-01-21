import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import time

# --- Configuração da Página ---
st.set_page_config(page_title="Sagrado Doce - Sistema", layout="wide", page_icon="🍰")

# --- Conexão Otimizada (CACHED RESOURCE) ---
# O segredo da velocidade: Conecta uma vez e mantém a conexão viva no cache do servidor.
@st.cache_resource
def init_connection():
    try:
        return psycopg2.connect(st.secrets["SUPABASE_URL"])
    except Exception as e:
        st.error(f"Erro ao conectar no banco: {e}")
        return None

conn = init_connection()

# --- Função de Execução Rápida ---
def run_query(query, params=None):
    # Se a conexão caiu, tenta reconectar uma vez
    global conn
    if conn.closed != 0:
        st.cache_resource.clear()
        conn = init_connection()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        try:
            cur.execute(query, params)
            conn.commit()
            
            # Se for SELECT
            if query.strip().upper().startswith("SELECT"):
                return cur.fetchall()
            
            # Se for INSERT pedindo ID
            if "RETURNING id" in query.lower():
                return cur.fetchone()['id']
                
        except psycopg2.DatabaseError as e:
            conn.rollback() # Desfaz se der erro
            st.error(f"Erro de SQL: {e}")
            return None

# --- Inicialização do Banco ---
def init_db():
    # Tabelas
    create_tables = [
        '''CREATE TABLE IF NOT EXISTS insumos (id SERIAL PRIMARY KEY, nome TEXT, unidade_medida TEXT, custo_total REAL, qtd_embalagem REAL, fator_conversao REAL, custo_unitario REAL, estoque_atual REAL DEFAULT 0, estoque_minimo REAL DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS receitas (id SERIAL PRIMARY KEY, nome TEXT, preco_venda REAL, custo_total REAL)''',
        '''CREATE TABLE IF NOT EXISTS receita_itens (id SERIAL PRIMARY KEY, receita_id INTEGER, insumo_id INTEGER, qtd_usada REAL, custo_item REAL, FOREIGN KEY(receita_id) REFERENCES receitas(id), FOREIGN KEY(insumo_id) REFERENCES insumos(id))''',
        '''CREATE TABLE IF NOT EXISTS vendas (id SERIAL PRIMARY KEY, cliente TEXT, data_pedido TIMESTAMP, tipo_entrega TEXT, endereco TEXT, forma_pagamento TEXT, itens_resumo TEXT, total_venda REAL, status TEXT, status_pagamento TEXT DEFAULT 'Pendente')''',
        '''CREATE TABLE IF NOT EXISTS venda_itens (id SERIAL PRIMARY KEY, venda_id INTEGER, receita_id INTEGER, qtd INTEGER, FOREIGN KEY(venda_id) REFERENCES vendas(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''',
        '''CREATE TABLE IF NOT EXISTS caixa (id SERIAL PRIMARY KEY, descricao TEXT, valor REAL, data_movimento TIMESTAMP, tipo TEXT, categoria TEXT)''',
        '''CREATE TABLE IF NOT EXISTS orcamentos (id SERIAL PRIMARY KEY, cliente TEXT, data_emissao TEXT, validade TEXT, total REAL, itens_resumo TEXT)''',
        '''CREATE TABLE IF NOT EXISTS vendedoras (id SERIAL PRIMARY KEY, nome TEXT)''',
        '''CREATE TABLE IF NOT EXISTS consignacoes (id SERIAL PRIMARY KEY, vendedora_id INTEGER, receita_id INTEGER, qtd_entregue REAL, qtd_vendida REAL DEFAULT 0, data_entrega TIMESTAMP, FOREIGN KEY(vendedora_id) REFERENCES vendedoras(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))'''
    ]
    for q in create_tables:
        run_query(q)
    
    # Migração segura para coluna estoque_minimo
    try:
        run_query("ALTER TABLE insumos ADD COLUMN estoque_minimo REAL DEFAULT 0")
    except:
        pass 

if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# --- Funções de Negócio ---
def baixar_estoque_por_venda(receita_id, qtd_vendida):
    ingredientes = run_query("SELECT insumo_id, qtd_usada FROM receita_itens WHERE receita_id = %s", (receita_id,))
    if ingredientes:
        for item in ingredientes:
            total_descontar = float(item['qtd_usada']) * float(qtd_vendida)
            run_query("UPDATE insumos SET estoque_atual = estoque_atual - %s WHERE id = %s", (total_descontar, item['insumo_id']))

def format_currency(value): return f"R$ {float(value):,.2f}"

def limpar_sessao(keys):
    for k in keys: 
        if k in st.session_state: del st.session_state[k]

# --- CSS ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    .status-ok { color: #28a745; font-weight: bold; }
    .status-alert { color: #dc3545; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- APP ---
st.title("🍰 Sagrado Doce - Gestão")

tab1, tab2, tab_estoque, tab_orc, tab3, tab4, tab_compras, tab_caixa = st.tabs([
    "📦 Insumos", "📒 Receitas", "📊 Estoque", "📑 Orçamentos", "🛒 Vendas", "📋 Produção", "🛍️ Compras", "💰 Financeiro"
])

# ================= ABA 1: INSUMOS =================
with tab1:
    st.header("Insumos")
    col1, col2 = st.columns(2)
    with col1:
        nome_insumo = st.text_input("Nome", key="in_nome")
        unidade_tipo = st.selectbox("Unidade Uso", ["g (Gramas)", "mL (Mililitros)", "un (Unidade)"], key="in_unidade")
        minimo = st.number_input("Estoque Mínimo", min_value=0.0)
    with col2:
        custo_embalagem = st.number_input("Custo Emb. (R$)", min_value=0.0, format="%.2f", key="in_custo")
        qtd_embalagem = st.number_input("Qtd Emb.", min_value=0.0, format="%.2f", key="in_qtd")
        unidade_compra = st.selectbox("Unidade Compra", ["kg", "g", "L", "mL", "un"], key="in_un_compra")

    if st.button("Salvar Insumo"):
        if nome_insumo and custo_embalagem and qtd_embalagem:
            qtd_total_base = qtd_embalagem * 1000 if unidade_compra in ["kg", "L"] else qtd_embalagem
            custo_unitario_calc = custo_embalagem / qtd_total_base
            run_query("INSERT INTO insumos (nome, unidade_medida, custo_total, qtd_embalagem, fator_conversao, custo_unitario, estoque_atual, estoque_minimo) VALUES (%s, %s, %s, %s, %s, %s, 0, %s)",
                      (nome_insumo, unidade_tipo.split()[0], float(custo_embalagem), float(qtd_total_base), 1, float(custo_unitario_calc), float(minimo)))
            st.success("Salvo!"); time.sleep(0.1); st.rerun()
    
    with st.expander("Excluir Insumo"):
        data = run_query("SELECT id, nome FROM insumos ORDER BY nome")
        if data:
            df_del = pd.DataFrame(data)
            sel_del = st.selectbox("Item", df_del['nome'])
            if st.button("Excluir"):
                iid = df_del[df_del['nome'] == sel_del]['id'].values[0]
                run_query("DELETE FROM insumos WHERE id=%s", (int(iid),))
                st.success("Excluído!"); time.sleep(0.1); st.rerun()

    data = run_query("SELECT nome, unidade_medida, estoque_minimo, custo_unitario FROM insumos ORDER BY nome")
    if data: st.dataframe(pd.DataFrame(data), use_container_width=True)

# ================= ABA 2: RECEITAS =================
with tab2:
    st.header("Receitas")
    if 'ingredientes_temp' not in st.session_state: st.session_state.ingredientes_temp = []
    
    data = run_query("SELECT id, nome FROM receitas ORDER BY nome")
    df_rec = pd.DataFrame(data) if data else pd.DataFrame()
    
    modo = st.radio("Ação:", ["Nova", "Editar"], horizontal=True)
    
    if modo == "Editar" and not df_rec.empty:
        sel_rec = st.selectbox("Receita", df_rec['nome'])
        if st.button("Carregar"):
            rid = df_rec[df_rec['nome'] == sel_rec]['id'].values[0]
            rdata = run_query("SELECT * FROM receitas WHERE id=%s", (int(rid),))[0]
            idata = run_query("SELECT ri.insumo_id, i.nome, ri.qtd_usada, i.unidade_medida, i.custo_unitario FROM receita_itens ri JOIN insumos i ON ri.insumo_id = i.id WHERE ri.receita_id=%s", (int(rid),))
            st.session_state.edit_id = int(rid)
            st.session_state.rec_nome = rdata['nome']
            st.session_state.rec_preco = rdata['preco_venda']
            st.session_state.ingredientes_temp = []
            if idata:
                for i in idata:
                    st.session_state.ingredientes_temp.append({
                        'id': i['insumo_id'], 'nome': i['nome'], 'qtd': i['qtd_usada'], 
                        'unidade': i['unidade_medida'], 'custo': i['qtd_usada'] * i['custo_unitario'], 'custo_unit': i['custo_unitario']
                    })
            st.rerun()

    c1, c2 = st.columns([1, 2])
    nome_rec = c1.text_input("Nome Receita", key="rec_nome" if 'rec_nome' in st.session_state else "n_rec")
    preco_rec = c2.number_input("Preço Venda", min_value=0.0, key="rec_preco" if 'rec_preco' in st.session_state else "p_rec")

    # Add Ingrediente
    data_ins = run_query("SELECT id, nome, unidade_medida, custo_unitario FROM insumos ORDER BY nome")
    if data_ins:
        df_ins = pd.DataFrame(data_ins)
        c1, c2, c3 = st.columns([2, 1, 1])
        isel = c1.selectbox("Insumo", df_ins['nome'])
        idat = df_ins[df_ins['nome'] == isel].iloc[0]
        iqtd = c2.number_input(f"Qtd ({idat['unidade_medida']})", min_value=0.0)
        if c3.button("➕"):
            st.session_state.ingredientes_temp.append({
                'id': int(idat['id']), 'nome': isel, 'qtd': float(iqtd), 
                'unidade': idat['unidade_medida'], 'custo': float(iqtd * idat['custo_unitario']), 'custo_unit': float(idat['custo_unitario'])
            })
            st.rerun()

    # Lista Itens
    if st.session_state.ingredientes_temp:
        for idx, item in enumerate(st.session_state.ingredientes_temp):
            st.text(f"{item['qtd']}{item['unidade']} - {item['nome']} (R$ {item['custo']:.2f})")
            if st.button("🗑️", key=f"d_{idx}"): st.session_state.ingredientes_temp.pop(idx); st.rerun()
        
        custo_tot = sum(i['custo'] for i in st.session_state.ingredientes_temp)
        st.info(f"Custo Total: {format_currency(custo_tot)}")
        
        if st.button("💾 Salvar Receita"):
            if 'edit_id' in st.session_state:
                run_query("UPDATE receitas SET nome=%s, preco_venda=%s, custo_total=%s WHERE id=%s", (nome_rec, preco_rec, custo_tot, st.session_state.edit_id))
                run_query("DELETE FROM receita_itens WHERE receita_id=%s", (st.session_state.edit_id,))
                rid = st.session_state.edit_id
                del st.session_state.edit_id
            else:
                rid = run_query("INSERT INTO receitas (nome, preco_venda, custo_total) VALUES (%s, %s, %s) RETURNING id", (nome_rec, preco_rec, custo_tot))
            
            for i in st.session_state.ingredientes_temp:
                run_query("INSERT INTO receita_itens (receita_id, insumo_id, qtd_usada, custo_item) VALUES (%s, %s, %s, %s)", (int(rid), int(i['id']), float(i['qtd']), float(i['custo'])))
            
            st.session_state.ingredientes_temp = []
            st.success("Salvo!"); time.sleep(0.1); st.rerun()

# ================= ABA 3: ESTOQUE =================
with tab_estoque:
    st.header("Estoque")
    data = run_query("SELECT id, nome, unidade_medida, estoque_atual, estoque_minimo FROM insumos ORDER BY nome")
    if data:
        df = pd.DataFrame(data)
        
        # Ajuste Rápido
        c1, c2 = st.columns([2, 1])
        isel = c1.selectbox("Item", df['nome'], key="s_stk")
        iqtd = c2.number_input("Ajuste (+/-)", step=1.0)
        if st.button("Atualizar Estoque"):
            iid = df[df['nome'] == isel]['id'].values[0]
            run_query("UPDATE insumos SET estoque_atual = estoque_atual + %s WHERE id=%s", (iqtd, int(iid)))
            st.success("Atualizado!"); time.sleep(0.1); st.rerun()
            
        st.dataframe(df, use_container_width=True)

# ================= ABA 4: ORÇAMENTOS =================
with tab_orc:
    st.header("Orçamentos")
    col1, col2 = st.columns([1, 2])
    cli = col1.text_input("Cliente")
    if 'cart_orc' not in st.session_state: st.session_state.cart_orc = []
    
    # Add Item
    data = run_query("SELECT nome, preco_venda FROM receitas ORDER BY nome")
    if data:
        df = pd.DataFrame(data)
        oprod = col2.selectbox("Produto", df['nome'], key="o_prod")
        oqtd = col2.number_input("Qtd", min_value=1, key="o_qtd")
        if col2.button("Add"):
            pr = df[df['nome'] == oprod]['preco_venda'].values[0]
            st.session_state.cart_orc.append({'Produto': oprod, 'Qtd': oqtd, 'Unit': pr, 'Total': oqtd*pr})
            st.rerun()

    if st.session_state.cart_orc:
        st.dataframe(pd.DataFrame(st.session_state.cart_orc), use_container_width=True)
        st.metric("Total", format_currency(sum(x['Total'] for x in st.session_state.cart_orc)))
        if st.button("Limpar"): st.session_state.cart_orc = []; st.rerun()

# ================= ABA 5: VENDAS =================
with tab3:
    st.header("Vendas")
    if 'cart_venda' not in st.session_state: st.session_state.cart_venda = []
    
    col1, col2 = st.columns(2)
    cli = col1.text_input("Cliente", key="v_cli")
    pagto = col2.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"])
    
    data = run_query("SELECT id, nome, preco_venda FROM receitas ORDER BY nome")
    if data:
        df = pd.DataFrame(data)
        vprod = st.selectbox("Produto", df['nome'], key="v_prod")
        vqtd = st.number_input("Qtd", min_value=1, key="v_qtd")
        
        if st.button("Adicionar ao Carrinho"):
            item = df[df['nome'] == vprod].iloc[0]
            st.session_state.cart_venda.append({'id': int(item['id']), 'nome': vprod, 'qtd': vqtd, 'total': vqtd * item['preco_venda']})
            st.rerun()
            
    if st.session_state.cart_venda:
        st.dataframe(pd.DataFrame(st.session_state.cart_venda), use_container_width=True)
        tot = sum(x['total'] for x in st.session_state.cart_venda)
        st.metric("Total Venda", format_currency(tot))
        
        if st.button("✅ Finalizar Pedido"):
            resumo = ", ".join([f"{x['qtd']}x {x['nome']}" for x in st.session_state.cart_venda])
            vid = run_query("INSERT INTO vendas (cliente, data_pedido, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (%s, NOW(), %s, %s, %s, 'Em Produção', 'Pendente') RETURNING id",
                      (cli, pagto, resumo, float(tot)))
            for x in st.session_state.cart_venda:
                run_query("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (%s, %s, %s)", (vid, x['id'], x['qtd']))
                baixar_estoque_por_venda(x['id'], x['qtd'])
            
            st.session_state.cart_venda = []
            st.success("Venda Realizada!"); time.sleep(0.1); st.rerun()

# ================= ABA 6: PRODUÇÃO =================
with tab4:
    st.header("Produção")
    st_filtro = st.radio("Status", ["Em Produção", "Concluído"], horizontal=True)
    data = run_query(f"SELECT * FROM vendas WHERE status='{st_filtro}' ORDER BY id DESC")
    if data:
        for r in data:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**#{r['id']} {r['cliente']}** - {r['itens_resumo']}")
                if r['status'] == "Em Produção":
                    if c2.button("Concluir", key=f"ok_{r['id']}"):
                        run_query("UPDATE vendas SET status='Concluído' WHERE id=%s", (r['id'],))
                        st.rerun()

# ================= ABA 7: COMPRAS (MRP) =================
with tab_compras:
    st.header("Planejamento de Compras (MRP)")
    
    # 1. Busca vendas em produção
    vendas = run_query("SELECT id FROM vendas WHERE status='Em Produção'")
    ids = tuple([v['id'] for v in vendas]) if vendas else "(0)"
    if len(ids) == 1 and ids != "(0)": ids = f"({ids[0]})"
    else: ids = str(ids)
    
    # 2. Query MRP
    q = f"""
        SELECT i.nome, i.estoque_atual, i.estoque_minimo, i.unidade_medida, i.custo_unitario, 
               COALESCE(SUM(ri.qtd_usada * vi.qtd), 0) as precisa_producao
        FROM insumos i
        LEFT JOIN (
            SELECT ri.insumo_id, ri.qtd_usada, vi.qtd 
            FROM venda_itens vi
            JOIN receita_itens ri ON vi.receita_id = ri.receita_id
            WHERE vi.venda_id IN {ids}
        ) as consumo ON i.id = consumo.insumo_id
        GROUP BY i.nome, i.estoque_atual, i.estoque_minimo, i.unidade_medida, i.custo_unitario
    """
    data = run_query(q)
    if data:
        df = pd.DataFrame(data)
        df['Necessário'] = df['precisa_producao'] + df['estoque_minimo']
        df['Comprar'] = df.apply(lambda x: max(0, x['Necessário'] - x['estoque_atual']), axis=1)
        df['Custo Est.'] = df['Comprar'] * df['custo_unitario']
        
        falta = df[df['Comprar'] > 0]
        if not falta.empty:
            st.error(f"🚨 Comprar: {format_currency(falta['Custo Est.'].sum())}")
            st.dataframe(falta[['nome', 'estoque_atual', 'estoque_minimo', 'Comprar', 'Custo Est.']], use_container_width=True)
        else:
            st.success("Estoque Suficiente.")
            
        with st.expander("Ver Tudo"):
            st.dataframe(df, use_container_width=True)

# ================= ABA 8: FINANCEIRO =================
with tab_caixa:
    st.header("Financeiro")
    
    # Pendentes
    data = run_query("SELECT id, cliente, total_venda FROM vendas WHERE status_pagamento='Pendente'")
    if data:
        st.warning("Receber Pendentes:")
        for r in data:
            c1, c2 = st.columns([3, 1])
            c1.write(f"#{r['id']} {r['cliente']} ({format_currency(r['total_venda'])})")
            if c2.button("Receber", key=f"pg_{r['id']}"):
                run_query("UPDATE vendas SET status_pagamento='Pago' WHERE id=%s", (r['id'],))
                run_query("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), 'Entrada', 'Vendas')", (f"Venda #{r['id']}", r['total_venda']))
                st.rerun()
    
    st.divider()
    
    # Lançamento
    with st.expander("Lançamento Manual"):
        l1, l2, l3 = st.columns(3)
        tipo = l1.radio("Tipo", ["Saída", "Entrada"])
        desc = l2.text_input("Descrição")
        val = l2.number_input("Valor", min_value=0.0)
        cat = l3.selectbox("Categoria", ["Mercado", "Cia do Doce", "Embalagem", "Insumos", "Contas Fixas", "Outros"])
        if l3.button("Lançar"):
            run_query("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), %s, %s)", (desc, val, tipo, cat))
            st.rerun()

    # Dashboard
    data = run_query("SELECT * FROM caixa")
    if data:
        df = pd.DataFrame(data)
        
        # Métricas
        ent = df[df['tipo']=='Entrada']['valor'].sum()
        sai = df[df['tipo']=='Saída']['valor'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", format_currency(ent))
        c2.metric("Saídas", format_currency(sai))
        c3.metric("Saldo", format_currency(ent-sai))
        
        # Gráficos
        st.subheader("Despesas por Categoria")
        desp = df[df['tipo']=='Saída']
        if not desp.empty:
            st.bar_chart(desp.groupby('categoria')['valor'].sum())
            
        st.dataframe(df.sort_values('id', ascending=False), use_container_width=True)

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

# --- Função de Conexão (MODO BLINDADO COM RE-TENTATIVA) ---
# MANTIDA A ESTRUTURA ORIGINAL QUE FUNCIONOU
def get_db_connection():
    try:
        db_url = st.secrets["SUPABASE_URL"]
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        st.stop()

def run_query(query, params=None):
    for tentativa in range(2):
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                conn.commit()
                
                if query.strip().upper().startswith("SELECT"):
                    result = cur.fetchall()
                    conn.close()
                    return result
                
                if "RETURNING id" in query.lower():
                    result = cur.fetchone()['id']
                    conn.close()
                    return result
            
            conn.close()
            return None

        except psycopg2.OperationalError:
            if conn: conn.close()
            time.sleep(1) # Pequena pausa para garantir reconexão
            continue 
            
        except Exception as e:
            if conn: conn.close()
            # Ignora erro se a coluna já existir (migração)
            if "already exists" in str(e): return None
            st.error(f"Erro no Banco: {e}")
            return None

# --- Inicialização do Banco de Dados ---
def init_db():
    # Cria as tabelas básicas
    run_query('''CREATE TABLE IF NOT EXISTS insumos (id SERIAL PRIMARY KEY, nome TEXT, unidade_medida TEXT, custo_total REAL, qtd_embalagem REAL, fator_conversao REAL, custo_unitario REAL, estoque_atual REAL DEFAULT 0, estoque_minimo REAL DEFAULT 0)''')
    run_query('''CREATE TABLE IF NOT EXISTS receitas (id SERIAL PRIMARY KEY, nome TEXT, preco_venda REAL, custo_total REAL)''')
    run_query('''CREATE TABLE IF NOT EXISTS receita_itens (id SERIAL PRIMARY KEY, receita_id INTEGER, insumo_id INTEGER, qtd_usada REAL, custo_item REAL, FOREIGN KEY(receita_id) REFERENCES receitas(id), FOREIGN KEY(insumo_id) REFERENCES insumos(id))''')
    run_query('''CREATE TABLE IF NOT EXISTS vendas (id SERIAL PRIMARY KEY, cliente TEXT, data_pedido TIMESTAMP, tipo_entrega TEXT, endereco TEXT, forma_pagamento TEXT, itens_resumo TEXT, total_venda REAL, status TEXT, status_pagamento TEXT DEFAULT 'Pendente')''')
    run_query('''CREATE TABLE IF NOT EXISTS venda_itens (id SERIAL PRIMARY KEY, venda_id INTEGER, receita_id INTEGER, qtd INTEGER, FOREIGN KEY(venda_id) REFERENCES vendas(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    run_query('''CREATE TABLE IF NOT EXISTS caixa (id SERIAL PRIMARY KEY, descricao TEXT, valor REAL, data_movimento TIMESTAMP, tipo TEXT, categoria TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS orcamentos (id SERIAL PRIMARY KEY, cliente TEXT, data_emissao TEXT, validade TEXT, total REAL, itens_resumo TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS vendedoras (id SERIAL PRIMARY KEY, nome TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS consignacoes (id SERIAL PRIMARY KEY, vendedora_id INTEGER, receita_id INTEGER, qtd_entregue REAL, qtd_vendida REAL DEFAULT 0, data_entrega TIMESTAMP, FOREIGN KEY(vendedora_id) REFERENCES vendedoras(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    
    # Migração Automática: Tenta adicionar coluna estoque_minimo se não existir (para quem já tem o banco criado)
    try:
        run_query("ALTER TABLE insumos ADD COLUMN estoque_minimo REAL DEFAULT 0")
    except:
        pass 

if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# --- Funções Auxiliares ---
def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode()
    return None

def limpar_sessao(keys):
    for key in keys:
        if key in st.session_state: del st.session_state[key]

def format_currency(value): return f"R$ {float(value):,.2f}"

# --- FUNÇÃO INTEELIGENTE: BAIXA DE ESTOQUE ---
def baixar_estoque_por_venda(receita_id, qtd_vendida):
    ingredientes = run_query("SELECT insumo_id, qtd_usada FROM receita_itens WHERE receita_id = %s", (receita_id,))
    if ingredientes:
        for item in ingredientes:
            total_descontar = float(item['qtd_usada']) * float(qtd_vendida)
            run_query("UPDATE insumos SET estoque_atual = estoque_atual - %s WHERE id = %s", (total_descontar, item['insumo_id']))

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
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- Interface Principal ---
st.title("🍰 Sagrado Doce - Gestão")

# Adicionada a aba "Compras"
tab1, tab2, tab_estoque, tab_orc, tab3, tab4, tab_compras, tab_caixa = st.tabs([
    "📦 Insumos", "📒 Receitas", "📊 Estoque", "📑 Orçamentos", "🛒 Vendas", "📋 Produção", "🛍️ Compras", "💰 Financeiro"
])

# ================= ABA 1: INSUMOS =================
with tab1:
    st.header("Cadastro de Insumos")
    col1, col2 = st.columns(2)
    with col1:
        nome_insumo = st.text_input("Nome", key="in_nome")
        unidade_tipo = st.selectbox("Unidade Uso", ["g (Gramas)", "mL (Mililitros)", "un (Unidade)"], key="in_unidade")
        # NOVO: Estoque Mínimo
        minimo = st.number_input("Estoque Mínimo (Alerta)", min_value=0.0, help="Quantidade mínima para não faltar")
    with col2:
        custo_embalagem = st.number_input("Custo Embalagem (R$)", min_value=0.0, format="%.2f", value=None, key="in_custo")
        qtd_embalagem = st.number_input("Qtd Embalagem", min_value=0.0, format="%.2f", value=None, key="in_qtd")
        unidade_compra = st.selectbox("Unidade Compra", ["kg", "g", "L", "mL", "un"], key="in_un_compra")

    if st.button("Salvar Insumo"):
        if nome_insumo and custo_embalagem and qtd_embalagem:
            qtd_total_base = qtd_embalagem * 1000 if unidade_compra in ["kg", "L"] else qtd_embalagem
            custo_unitario_calc = custo_embalagem / qtd_total_base
            # ATUALIZADO: Inclui estoque_minimo no insert
            run_query("INSERT INTO insumos (nome, unidade_medida, custo_total, qtd_embalagem, fator_conversao, custo_unitario, estoque_atual, estoque_minimo) VALUES (%s, %s, %s, %s, %s, %s, 0, %s)",
                      (nome_insumo, unidade_tipo.split()[0], float(custo_embalagem), float(qtd_total_base), 1, float(custo_unitario_calc), float(minimo)))
            st.success("Salvo!"); limpar_sessao(["in_nome", "in_custo", "in_qtd"]); st.rerun()
    
    st.divider()
    with st.expander("🗑️ Excluir Insumo"):
        data = run_query("SELECT id, nome FROM insumos ORDER BY nome")
        insumos_del = pd.DataFrame(data) if data else pd.DataFrame()
        if not insumos_del.empty:
            sel_del_ins = st.selectbox("Selecione para excluir:", insumos_del['nome'], key="sel_del_ins")
            if st.button("Excluir Insumo Selecionado"):
                id_del = insumos_del[insumos_del['nome'] == sel_del_ins]['id'].values[0]
                run_query("DELETE FROM insumos WHERE id=%s", (int(id_del),))
                st.success("Excluído!"); st.rerun()

    data = run_query("SELECT nome, unidade_medida, estoque_minimo, custo_unitario FROM insumos ORDER BY nome")
    if data: st.dataframe(pd.DataFrame(data), use_container_width=True)

# ================= ABA 2: RECEITAS =================
with tab2:
    st.header("Gerenciar Receitas")
    if 'ingredientes_temp' not in st.session_state: st.session_state.ingredientes_temp = []
    if 'editando_id' not in st.session_state: st.session_state.editando_id = None 
    
    data = run_query("SELECT id, nome FROM receitas ORDER BY nome")
    receitas_existentes = pd.DataFrame(data) if data else pd.DataFrame()
    modo_receita = st.radio("Ação:", ["Nova (Do Zero)", "Clonar/Escalar", "Editar Existente"], horizontal=True)

    if modo_receita in ["Clonar/Escalar", "Editar Existente"] and not receitas_existentes.empty:
        sel_receita_nome = st.selectbox("Selecione a Receita", receitas_existentes['nome'])
        if st.button("Carregar Dados"):
            rec_id = receitas_existentes[receitas_existentes['nome'] == sel_receita_nome]['id'].values[0]
            rec_data = run_query("SELECT * FROM receitas WHERE id = %s", (int(rec_id),))[0]
            itens_data = run_query("SELECT ri.insumo_id, i.nome, ri.qtd_usada, i.unidade_medida, i.custo_unitario FROM receita_itens ri JOIN insumos i ON ri.insumo_id = i.id WHERE ri.receita_id = %s", (int(rec_id),))
            st.session_state.ingredientes_temp = []
            if itens_data:
                for item in itens_data:
                    st.session_state.ingredientes_temp.append({
                        'id': item['insumo_id'], 'nome': item['nome'], 'qtd': item['qtd_usada'], 
                        'unidade': item['unidade_medida'], 'custo': item['qtd_usada'] * item['custo_unitario'], 
                        'custo_unitario': item['custo_unitario']
                    })
            if modo_receita == "Editar Existente":
                st.session_state.editando_id = int(rec_id)
                st.session_state['rec_nome_in'] = rec_data['nome']; st.session_state['rec_venda_in'] = rec_data['preco_venda']
                st.toast(f"Editando: {rec_data['nome']}")
            else:
                st.session_state.editando_id = None 
                st.session_state['rec_nome_in'] = f"{rec_data['nome']} (Cópia)"; st.session_state['rec_venda_in'] = 0.0
                st.toast("Clonado.")

    if modo_receita == "Nova (Do Zero)" and st.session_state.get('rec_nome_in') != "" and st.session_state.editando_id is not None:
         st.session_state.editando_id = None; st.session_state.ingredientes_temp = []
         limpar_sessao(['rec_nome_in', 'rec_venda_in'])

    c1, c2 = st.columns([1, 2])
    with c1: nome_receita = st.text_input("Nome da Receita", key="rec_nome_in")
    with c2: preco_venda = st.number_input("Preço Venda (R$)", min_value=0.0, key="rec_venda_in")

    data_ins = run_query("SELECT id, nome, unidade_medida, custo_unitario FROM insumos ORDER BY nome")
    insumos_db = pd.DataFrame(data_ins) if data_ins else pd.DataFrame()
    if not insumos_db.empty:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1: insumo_sel = st.selectbox("Insumo", insumos_db['nome'], key="rec_ins_sel")
        with c2: 
            dat = insumos_db[insumos_db['nome'] == insumo_sel].iloc[0]
            qtd_add = st.number_input(f"Qtd ({dat['unidade_medida']})", min_value=0.0, key="rec_qtd_add")
        with c3:
            st.write(""); st.write("")
            if st.button("➕"):
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
        with col_act1:
            txt_btn = "💾 Salvar Alterações" if modo_receita == "Editar Existente" else "💾 Criar Nova Receita"
            if st.button(txt_btn, type="primary"):
                if not st.session_state.rec_nome_in: st.error("Nome vazio!"); st.stop()
                
                v_preco = float(st.session_state.rec_venda_in)
                v_custo = float(custo_total)

                if modo_receita == "Editar Existente" and st.session_state.editando_id:
                    run_query("UPDATE receitas SET nome=%s, preco_venda=%s, custo_total=%s WHERE id=%s", 
                              (st.session_state.rec_nome_in, v_preco, v_custo, st.session_state.editando_id))
                    run_query("DELETE FROM receita_itens WHERE receita_id=%s", (st.session_state.editando_id,))
                    final_id = st.session_state.editando_id
                    msg = "Receita Atualizada!"
                else:
                    final_id = run_query("INSERT INTO receitas (nome, preco_venda, custo_total) VALUES (%s, %s, %s) RETURNING id", 
                              (st.session_state.rec_nome_in, v_preco, v_custo))
                    msg = "Nova Receita Criada!"
                
                if final_id:
                    for item in st.session_state.ingredientes_temp:
                        run_query("INSERT INTO receita_itens (receita_id, insumo_id, qtd_usada, custo_item) VALUES (%s, %s, %s, %s)", 
                                  (int(final_id), int(item['id']), float(item['qtd']), float(item['custo'])))
                    
                    st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
                    limpar_sessao(['rec_nome_in', 'rec_venda_in', 'rec_qtd_add']); st.success(msg); st.rerun()
                else:
                    st.error("Erro ao salvar receita.")
        
        with col_act2:
            if modo_receita == "Editar Existente" and st.session_state.editando_id:
                if st.button("❌ Excluir Receita", key="btn_del_rec"):
                    id_para_apagar = st.session_state.editando_id
                    run_query("DELETE FROM receitas WHERE id=%s", (id_para_apagar,))
                    run_query("DELETE FROM receita_itens WHERE receita_id=%s", (id_para_apagar,))
                    st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
                    limpar_sessao(['rec_nome_in', 'rec_venda_in'])
                    st.success("Excluída!"); st.rerun()

# ================= ABA 3: ESTOQUE (COM GESTÃO COMPLETA E MÍNIMO) =================
with tab_estoque:
    st.header("Gerenciar Estoque")
    
    data = run_query("SELECT id, nome, unidade_medida, estoque_atual, estoque_minimo, custo_unitario, custo_total, qtd_embalagem FROM insumos ORDER BY nome")
    insumos = pd.DataFrame(data) if data else pd.DataFrame()
    
    if not insumos.empty:
        # 1. Movimentação Rápida
        st.subheader("⚡ Ajuste Rápido (Entrada/Perda)")
        c1, c2 = st.columns([2, 1])
        with c1:
            sel_mov = st.selectbox("Selecione o Insumo", insumos['nome'], key="stk_sel")
        with c2:
            qtd_mov = st.number_input("Qtd Adicionar/Remover (+/-)", step=1.0, key="stk_qtd")
        
        if st.button("Atualizar Quantidade"):
            iid = insumos[insumos['nome'] == sel_mov]['id'].values[0]
            run_query("UPDATE insumos SET estoque_atual = estoque_atual + %s WHERE id = %s", (float(qtd_mov), int(iid)))
            st.success(f"Estoque de {sel_mov} atualizado!"); st.rerun()
        
        st.divider()
        
        # 2. Edição de Cadastro e Mínimo
        st.subheader("✏️ Editar Cadastro (Valores e Mínimo)")
        with st.expander("Clique para editar nome, preço ou mínimo"):
            insumo_edit = st.selectbox("Qual insumo editar?", insumos['nome'], key="edit_sel")
            dados_atuais = insumos[insumos['nome'] == insumo_edit].iloc[0]
            
            with st.form("form_edit_insumo"):
                ce1, ce2 = st.columns(2)
                novo_nome = ce1.text_input("Nome", value=dados_atuais['nome'])
                # NOVO: Editar Mínimo
                novo_minimo = ce2.number_input("Estoque Mínimo (Alerta)", value=float(dados_atuais['estoque_minimo']), min_value=0.0)
                novo_custo_total = ce1.number_input("Custo da Embalagem (R$)", value=float(dados_atuais['custo_total']), min_value=0.0)
                nova_qtd_emb = ce2.number_input("Qtd na Embalagem", value=float(dados_atuais['qtd_embalagem']), min_value=0.0)
                novo_estoque = st.number_input("Correção Manual de Estoque (Total)", value=float(dados_atuais['estoque_atual']))
                
                if st.form_submit_button("Salvar Alterações"):
                    # Recalcula custo unitário
                    novo_custo_unit = novo_custo_total / nova_qtd_emb if nova_qtd_emb > 0 else 0
                    
                    run_query("""
                        UPDATE insumos 
                        SET nome=%s, custo_total=%s, qtd_embalagem=%s, estoque_atual=%s, estoque_minimo=%s, custo_unitario=%s 
                        WHERE id=%s
                    """, (novo_nome, float(novo_custo_total), float(nova_qtd_emb), float(novo_estoque), float(novo_minimo), float(novo_custo_unit), int(dados_atuais['id'])))
                    st.success("Dados atualizados!"); st.rerun()
            
    st.dataframe(insumos[['nome', 'estoque_atual', 'estoque_minimo', 'unidade_medida']], use_container_width=True)

# ================= ABA 4: ORÇAMENTOS =================
with tab_orc:
    st.header("Orçamentos")
    col_orc1, col_orc2 = st.columns([1, 2])
    with col_orc1:
        orc_cliente = st.text_input("Cliente", key="orc_cli")
        orc_validade = st.selectbox("Validade", ["7 dias", "15 dias", "30 dias"])
    with col_orc2:
        if 'carrinho_orc' not in st.session_state: st.session_state.carrinho_orc = []
        tipo_item = st.radio("Adicionar:", ["Receita Cadastrada", "Item Personalizado (Avulso)"], horizontal=True)
        if tipo_item == "Receita Cadastrada":
            data = run_query("SELECT id, nome, preco_venda, custo_total FROM receitas ORDER BY nome")
            receitas_orc = pd.DataFrame(data) if data else pd.DataFrame()
            if not receitas_orc.empty:
                co1, co2, co3 = st.columns([2, 1, 1])
                prod_orc = co1.selectbox("Produto", receitas_orc['nome'], key="orc_prod")
                qtd_orc = co2.number_input("Qtd", min_value=1, value=1, key="orc_qtd")
                d_orc = receitas_orc[receitas_orc['nome'] == prod_orc].iloc[0]
                if co3.button("Add"):
                    st.session_state.carrinho_orc.append({
                        'produto': prod_orc, 'qtd': float(qtd_orc), 
                        'unitario': float(d_orc['preco_venda']), 'custo_unit': float(d_orc['custo_total']), 
                        'total': float(qtd_orc * d_orc['preco_venda'])
                    })
                    st.rerun()
        else:
            ca1, ca2, ca3 = st.columns(3)
            nome_avulso = ca1.text_input("Descrição do Item")
            custo_avulso = ca2.number_input("Custo Interno (R$)", min_value=0.0)
            preco_avulso = ca3.number_input("Preço de Venda (R$)", min_value=0.0)
            if st.button("Add Avulso"):
                if nome_avulso and preco_avulso:
                    st.session_state.carrinho_orc.append({
                        'produto': nome_avulso, 'qtd': 1.0, 
                        'unitario': float(preco_avulso), 'custo_unit': float(custo_avulso), 
                        'total': float(preco_avulso)
                    })
                    st.rerun()
                
    if st.session_state.carrinho_orc:
        st.divider()
        st.markdown("### Visão Interna")
        df_orc = pd.DataFrame(st.session_state.carrinho_orc)
        df_orc['Custo Total'] = df_orc['custo_unit'] * df_orc['qtd']
        df_orc['Lucro Est.'] = df_orc['total'] - df_orc['Custo Total']
        st.dataframe(df_orc[['produto', 'qtd', 'unitario', 'total', 'Custo Total', 'Lucro Est.']], use_container_width=True)
        
        total_original = df_orc['total'].sum()
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown(f"**Total Original: {format_currency(total_original)}**")
            valor_final_desejado = st.number_input("Valor Final com Desconto (R$)", value=float(total_original), step=1.0)
            desconto_reais = total_original - valor_final_desejado
            desconto_perc = (desconto_reais / total_original) * 100 if total_original > 0 else 0
            if desconto_reais > 0: st.caption(f"🔻 Desconto aplicado: {format_currency(desconto_reais)} ({desconto_perc:.1f}%)")
        with col_t2:
            st.metric("Total Final para Cliente", format_currency(valor_final_desejado))

        c_a1, c_a2 = st.columns(2)
        if c_a1.button("Limpar Orçamento"): st.session_state.carrinho_orc = []; st.rerun()
        
        if c_a2.button("📄 Gerar Folha do Cliente"):
            hoje = datetime.now().strftime("%d/%m/%Y")
            img_b64 = get_base64_image("logo.png") 
            logo_html = f'<div class="logo-container"><img src="data:image/png;base64,{img_b64}" class="logo-img"></div>' if img_b64 else '<div class="logo-container" style="font-size:40px">🍰</div>'
            itens_html = "".join([f"<tr><td>{i['produto']}</td><td>{i['qtd']}</td><td>{format_currency(i['unitario'])}</td><td>{format_currency(i['total'])}</td></tr>" for i in st.session_state.carrinho_orc])
            footer_table = f"""<tr class="total-row"><td colspan="3" style="text-align: right;">Total:</td><td>{format_currency(total_original)}</td></tr>"""
            if desconto_reais > 0:
                footer_table = f"""<tr><td colspan="3" class="subtotal-row">Subtotal:</td><td style="text-align: right;">{format_currency(total_original)}</td></tr><tr><td colspan="3" class="subtotal-row" style="color: red;">Desconto ({desconto_perc:.1f}%):</td><td style="text-align: right; color: red;">- {format_currency(desconto_reais)}</td></tr><tr class="total-row"><td colspan="3" style="text-align: right;">Total Final:</td><td>{format_currency(valor_final_desejado)}</td></tr>"""
            html = f"""<div class="invoice-box"><div class="header-top">{logo_html}<div class="header-title">Sagrado Doce</div></div><div style="margin:20px 0"><strong>Cliente:</strong> {orc_cliente}<br><strong>Data:</strong> {hoje}<br><strong>Validade:</strong> {orc_validade}</div><table class="table-custom"><tr class="heading"><th>Item</th><th>Qtd</th><th>Unit.</th><th>Total</th></tr>{itens_html}{footer_table}</table><div style="margin-top:40px; text-align:center; font-size:12px; color:#aaa;">Obrigado pela preferência!</div></div>"""
            st.markdown(html, unsafe_allow_html=True)

# ================= ABA 5: VENDAS (COM BAIXA AUTO) =================
with tab3:
    st.header("Vendas & Saídas")
    sub_tab_balcao, sub_tab_vendedoras = st.tabs(["🛒 Venda Balcão", "👜 Vendedoras / Consignado"])
    
    with sub_tab_balcao:
        c1, c2 = st.columns(2)
        with c1:
            cli = st.text_input("Cliente", key="v_cli")
            tipo = st.radio("Tipo", ["Retirada", "Entrega"], horizontal=True, key="v_tipo")
        with c2:
            pagto = st.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"], key="v_pagto")
            end = st.text_input("Endereço", key="v_end") if tipo == "Entrega" else ""

        st.divider()
        data = run_query("SELECT id, nome, preco_venda FROM receitas ORDER BY nome")
        receitas = pd.DataFrame(data) if data else pd.DataFrame()
        if not receitas.empty:
            prod = st.selectbox("Produto", receitas['nome'], key="v_prod")
            d_prod = receitas[receitas['nome'] == prod].iloc[0]
            qv = st.number_input("Qtd", min_value=1, key="v_qtd")
            
            if 'carrinho' not in st.session_state: st.session_state.carrinho = []
            if st.button("Add Carrinho", key="add_venda"):
                st.session_state.carrinho.append({
                    'id': int(d_prod['id']), 'produto': prod, 'qtd': float(qv), 
                    'total': float(qv * d_prod['preco_venda'])
                })
                st.rerun()

            if st.session_state.carrinho:
                df_c = pd.DataFrame(st.session_state.carrinho)
                st.dataframe(df_c[['qtd', 'produto', 'total']], use_container_width=True)
                tot = df_c['total'].sum()
                st.metric("Total", format_currency(tot))
                
                # FINALIZAR VENDA
                if st.button("✅ Confirmar Pedido", key="conf_venda"):
                    resumo = "; ".join([f"{x['qtd']}x {x['produto']}" for x in st.session_state.carrinho])
                    
                    # 1. Cria a Venda
                    vid = run_query("INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (%s, NOW(), %s, %s, %s, %s, %s, 'Em Produção', 'Pendente') RETURNING id", 
                              (cli, tipo, end, pagto, resumo, float(tot)))
                    
                    if vid:
                        for i in st.session_state.carrinho: 
                            # 2. Cria item da venda
                            run_query("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (%s, %s, %s)", (vid, int(i['id']), int(i['qtd'])))
                            
                            # 3. BAIXA AUTOMÁTICA DE ESTOQUE
                            # Chama a função que desconta os insumos dessa receita
                            baixar_estoque_por_venda(int(i['id']), float(i['qtd']))
                        
                        st.session_state.carrinho = []; limpar_sessao(['v_cli', 'v_end']); st.success("Pedido Feito e Estoque Atualizado!"); st.rerun()

    with sub_tab_vendedoras:
        col_vend1, col_vend2 = st.columns([1, 2])
        with col_vend1:
            st.subheader("Vendedora")
            novo_nome_vend = st.text_input("Cadastrar Nova Vendedora")
            if st.button("Cadastrar"):
                if novo_nome_vend: run_query("INSERT INTO vendedoras (nome) VALUES (%s)", (novo_nome_vend,)); st.success("Cadastrada!"); st.rerun()
            st.divider()
            data_vend = run_query("SELECT * FROM vendedoras ORDER BY nome")
            vendedoras_db = pd.DataFrame(data_vend) if data_vend else pd.DataFrame()
            if not vendedoras_db.empty:
                vendedora_sel_nome = st.selectbox("Selecionar Vendedora", vendedoras_db['nome'])
                vendedora_id = vendedoras_db[vendedoras_db['nome'] == vendedora_sel_nome]['id'].values[0]
                st.info(f"Gerenciando: **{vendedora_sel_nome}**")
                with st.expander("👜 Entregar Produtos (Sacola)"):
                    if not receitas.empty:
                        prod_entregar = st.selectbox("Produto para entregar", receitas['nome'], key="vend_prod")
                        id_prod_entregar = receitas[receitas['nome'] == prod_entregar]['id'].values[0]
                        qtd_entregar = st.number_input("Quantidade", min_value=1, key="vend_qtd")
                        if st.button("Entregar para Vendedora"):
                            run_query("INSERT INTO consignacoes (vendedora_id, receita_id, qtd_entregue, data_entrega) VALUES (%s, %s, %s, NOW())", 
                                         (int(vendedora_id), int(id_prod_entregar), float(qtd_entregar)))
                            st.success(f"Entregue {qtd_entregar}x {prod_entregar}"); st.rerun()
            else: st.warning("Cadastre uma vendedora.")

        with col_vend2:
            if not vendedoras_db.empty:
                st.subheader(f"Sacola de {vendedora_sel_nome}")
                query_sacola = f"SELECT c.id, r.nome, c.qtd_entregue, c.qtd_vendida, (c.qtd_entregue - c.qtd_vendida) as em_maos, r.preco_venda, r.id as rec_id FROM consignacoes c JOIN receitas r ON c.receita_id = r.id WHERE c.vendedora_id = {vendedora_id} AND (c.qtd_entregue - c.qtd_vendida) > 0"
                data_sc = run_query(query_sacola)
                sacola = pd.DataFrame(data_sc) if data_sc else pd.DataFrame()
                if not sacola.empty:
                    st.dataframe(sacola[['nome', 'qtd_entregue', 'qtd_vendida', 'em_maos']], use_container_width=True)
                    st.divider()
                    st.markdown("#### 📉 Registrar Venda (Baixa)")
                    col_baixa1, col_baixa2 = st.columns(2)
                    with col_baixa1:
                        item_baixa = st.selectbox("Produto vendido?", sacola['nome'] + " (ID: " + sacola['id'].astype(str) + ")")
                        id_consignacao = int(item_baixa.split("ID: ")[1].replace(")", ""))
                        dados_item = sacola[sacola['id'] == id_consignacao].iloc[0]
                        qtd_venda_vend = st.number_input("Qtd Vendida", min_value=1, max_value=int(dados_item['em_maos']))
                        pagto_vend = st.selectbox("Pagamento Recebido", ["Pix", "Dinheiro", "Cartão"], key="pg_vend")
                        receber_agora = st.checkbox("Dinheiro já está comigo? (Lançar no Caixa)", value=True)
                    with col_baixa2:
                        preco_orig = dados_item['preco_venda']
                        st.text(f"Preço Unit. Original: {format_currency(preco_orig)}")
                        desconto_un = st.number_input("Desconto por ITEM (R$)", min_value=0.0, value=0.0)
                        valor_final_un = preco_orig - desconto_un
                        total_venda_vend = valor_final_un * qtd_venda_vend
                        st.metric("Total desta Venda", format_currency(total_venda_vend))
                        if st.button("✅ Registrar Venda da Vendedora"):
                            # Atualiza consignado
                            run_query("UPDATE consignacoes SET qtd_vendida = qtd_vendida + %s WHERE id = %s", (float(qtd_venda_vend), id_consignacao))
                            
                            resumo_venda = f"{qtd_venda_vend}x {dados_item['nome']} (Via {vendedora_sel_nome})"
                            if desconto_un > 0: resumo_venda += f" [Desc: R${desconto_un}/un]"
                            status_pg = 'Pago' if receber_agora else 'Pendente'
                            vid = run_query("INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (%s, NOW(), 'Venda Externa', %s, %s, %s, %s, 'Concluído', %s) RETURNING id", 
                                      (f"Vend. {vendedora_sel_nome}", "N/A", pagto_vend, resumo_venda, float(total_venda_vend), status_pg))
                            run_query("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (%s, %s, %s)", (vid, int(dados_item['rec_id']), int(qtd_venda_vend)))
                            if receber_agora: run_query("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), 'Entrada', 'Vendas')", (f"Venda #{vid} - {vendedora_sel_nome}", float(total_venda_vend)))
                            st.success("Venda Registrada!"); st.rerun()
                else: st.info("Ela não tem produtos em mãos.")

# ================= ABA 6: PRODUÇÃO =================
with tab4:
    st.header("Produção")
    st_filtro = st.radio("Ver", ["Em Produção", "Concluídos"], horizontal=True)
    st_db = "Em Produção" if st_filtro == "Em Produção" else "Concluído"
    data = run_query(f"SELECT * FROM vendas WHERE status = '{st_db}' ORDER BY id DESC")
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
                        run_query("UPDATE vendas SET status='Concluído' WHERE id=%s", (r['id'],)); st.rerun()
                with c3.expander("Opções"):
                     if st.button("🗑️ Excluir Pedido", key=f"del_v_{r['id']}"):
                         run_query("DELETE FROM vendas WHERE id=%s", (r['id'],)); run_query("DELETE FROM venda_itens WHERE venda_id=%s", (r['id'],)); st.warning("Excluído"); st.rerun()
    else: st.info("Sem pedidos.")

# ================= ABA 7: LISTA DE COMPRAS (MRP AVANÇADO) =================
with tab_compras:
    st.header("🛍️ Planejamento de Compras (MRP)")
    st.info("Aqui você vê a separação exata entre o que precisa para os pedidos e para repor o estoque mínimo.")
    
    # 1. Pega todas as vendas pendentes de produção
    vendas_pendentes = run_query("SELECT id FROM vendas WHERE status = 'Em Produção'")
    
    # Monta lista de IDs ou usa "0" se não tiver nada
    ids_vendas = tuple([v['id'] for v in vendas_pendentes]) if vendas_pendentes else "(0)"
    if len(ids_vendas) == 1 and ids_vendas != "(0)": ids_vendas = f"({ids_vendas[0]})"
    else: ids_vendas = str(ids_vendas)
    
    # 2. SQL Mágico Completo (Com Estoque Mínimo)
    query_necessidade = f"""
        SELECT i.nome, i.estoque_atual, i.estoque_minimo, i.unidade_medida, i.custo_unitario, 
               COALESCE(SUM(ri.qtd_usada * vi.qtd), 0) as precisa_producao
        FROM insumos i
        LEFT JOIN (
            SELECT ri.insumo_id, ri.qtd_usada, vi.qtd 
            FROM venda_itens vi
            JOIN receita_itens ri ON vi.receita_id = ri.receita_id
            WHERE vi.venda_id IN {ids_vendas}
        ) as consumo ON i.id = consumo.insumo_id
        GROUP BY i.nome, i.estoque_atual, i.estoque_minimo, i.unidade_medida, i.custo_unitario
    """
    dados_mrp = run_query(query_necessidade)
    
    if dados_mrp:
        df_mrp = pd.DataFrame(dados_mrp)
        
        # Lógica MRP: (Precisa para Pedido + Mínimo para Segurança) - O que já tenho
        df_mrp['Total Necessário'] = df_mrp['precisa_producao'] + df_mrp['estoque_minimo']
        df_mrp['Saldo Final'] = df_mrp['estoque_atual'] - df_mrp['Total Necessário']
        df_mrp['Comprar'] = df_mrp['Saldo Final'].apply(lambda x: abs(x) if x < 0 else 0)
        df_mrp['Custo Est.'] = df_mrp['Comprar'] * df_mrp['custo_unitario']
        
        falta = df_mrp[df_mrp['Comprar'] > 0].copy()
        
        if not falta.empty:
            st.error(f"🚨 LISTA DE COMPRAS: Custo Estimado {format_currency(falta['Custo Est.'].sum())}")
            st.dataframe(falta[['nome', 'precisa_producao', 'estoque_minimo', 'estoque_atual', 'Comprar', 'unidade_medida', 'Custo Est.']], use_container_width=True)
        else:
            st.success("✅ Estoque está saudável! Nada para comprar.")
            
        with st.expander("Ver Todos os Itens (Mesmo os que não precisa comprar)"):
            st.dataframe(df_mrp[['nome', 'estoque_atual', 'estoque_minimo', 'precisa_producao', 'Comprar']], use_container_width=True)
        
        # Detalhe por Pedido (Micro Visão)
        st.divider()
        st.subheader("🔍 Consultar Insumos por Receita Vendida")
        if vendas_pendentes:
            venda_sel = st.selectbox("Selecione o Pedido Pendente", [f"{v['id']}" for v in vendas_pendentes])
            if venda_sel:
                q_micro = f"""
                    SELECT i.nome, (ri.qtd_usada * vi.qtd) as precisa_para_pedido, i.estoque_atual, i.unidade_medida
                    FROM venda_itens vi
                    JOIN receita_itens ri ON vi.receita_id = ri.receita_id
                    JOIN insumos i ON ri.insumo_id = i.id
                    WHERE vi.venda_id = {venda_sel}
                """
                micro = run_query(q_micro)
                if micro:
                    st.dataframe(pd.DataFrame(micro), use_container_width=True)
        else:
            st.info("Nenhum pedido pendente para consulta detalhada.")

# ================= ABA 8: CAIXA (COM GRÁFICOS) =================
with tab_caixa:
    st.header("Financeiro e Relatórios")
    
    # 1. Dashboard Gráfico
    data_cx_all = run_query("SELECT * FROM caixa")
    if data_cx_all:
        df_dash = pd.DataFrame(data_cx_all)
        
        c1, c2, c3 = st.columns(3)
        ent = df_dash[df_dash['tipo'] == 'Entrada']['valor'].sum()
        sai = df_dash[df_dash['tipo'] == 'Saída']['valor'].sum()
        c1.metric("Total Entradas", format_currency(ent))
        c2.metric("Total Saídas", format_currency(sai))
        c3.metric("Saldo Atual", format_currency(ent - sai))
        
        st.divider()
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Despesas por Categoria")
            gastos = df_dash[df_dash['tipo'] == 'Saída']
            if not gastos.empty:
                gastos_cat = gastos.groupby('categoria')['valor'].sum()
                st.bar_chart(gastos_cat)
            else: st.info("Sem despesas registradas.")
            
        with col_g2:
            st.subheader("Fluxo Recente")
            if not df_dash.empty:
                df_dash['data_movimento'] = pd.to_datetime(df_dash['data_movimento'])
                # Agrupar por dia para o gráfico ficar mais limpo
                fluxo_diario = df_dash.groupby([df_dash['data_movimento'].dt.date, 'tipo'])['valor'].sum().unstack().fillna(0)
                st.line_chart(fluxo_diario)

    st.divider()
    
    # 2. Pendentes
    st.subheader("A Receber (Vendas)")
    data_p = run_query("SELECT id, cliente, total_venda FROM vendas WHERE status_pagamento = 'Pendente'")
    pend = pd.DataFrame(data_p) if data_p else pd.DataFrame()
    if not pend.empty:
        for _, r in pend.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"#{r['id']} {r['cliente']} - {format_currency(r['total_venda'])}")
                if c2.button("Receber", key=f"rec_{r['id']}"):
                    run_query("UPDATE vendas SET status_pagamento='Pago' WHERE id=%s", (r['id'],))
                    run_query("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), 'Entrada', 'Vendas')", (f"Venda #{r['id']}", float(r['total_venda'])))
                    st.rerun()
    else: st.info("Nenhuma venda pendente.")
    
    st.divider()
    
    # 3. Lançamento Manual (Categorias Novas)
    with st.expander("💰 Lançamento Manual (Despesas/Entradas)", expanded=True):
        with st.form("form_cx_manual"):
            l1, l2, l3 = st.columns(3)
            tp = l1.radio("Tipo", ["Saída", "Entrada"])
            desc = l2.text_input("Descrição (Ex: Leite no Mercado)")
            val = l2.number_input("Valor", min_value=0.0)
            
            # Novas Categorias Solicitadas
            cats = ["Insumos", "Mercado", "Cia do Doce", "Embalagem", "Contas Fixas", "Vendas", "Outros"]
            cat = l3.selectbox("Categoria", cats)
            
            if st.form_submit_button("Lançar"): 
                run_query("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (%s, %s, NOW(), %s, %s)", (desc, float(val), tp, cat)); st.rerun()
    
    # 4. Extrato
    data_cx = run_query("SELECT * FROM caixa ORDER BY id DESC LIMIT 50")
    cx = pd.DataFrame(data_cx) if data_cx else pd.DataFrame()
    if not cx.empty:
        st.dataframe(cx, use_container_width=True)
        with st.expander("Gerenciar (Excluir Lançamento Errado)"):
            sel_cx_id = st.selectbox("Selecione ID para excluir:", cx['id'].astype(str) + " - " + cx['descricao'])
            if st.button("Excluir Lançamento Selecionado"):
                id_to_del = int(sel_cx_id.split(" - ")[0]); run_query("DELETE FROM caixa WHERE id=%s", (id_to_del,)); st.success("Excluído!"); st.rerun()


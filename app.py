import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import base64
import os

# --- Configuração da Página ---
st.set_page_config(page_title="Sagrado Doce - Sistema", layout="wide", page_icon="🍰")

# --- Função para Ler Imagem Local (Base64) ---
def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return None

# --- Banco de Dados ---
def init_db():
    conn = sqlite3.connect('confeitaria.db')
    c = conn.cursor()
    # Tabelas
    c.execute('''CREATE TABLE IF NOT EXISTS insumos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, unidade_medida TEXT, custo_total REAL, qtd_embalagem REAL, fator_conversao REAL, custo_unitario REAL, estoque_atual REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS receitas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, preco_venda REAL, custo_total REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS receita_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, receita_id INTEGER, insumo_id INTEGER, qtd_usada REAL, custo_item REAL, FOREIGN KEY(receita_id) REFERENCES receitas(id), FOREIGN KEY(insumo_id) REFERENCES insumos(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, data_pedido TEXT, tipo_entrega TEXT, endereco TEXT, forma_pagamento TEXT, itens_resumo TEXT, total_venda REAL, status TEXT, status_pagamento TEXT DEFAULT 'Pendente')''')
    c.execute('''CREATE TABLE IF NOT EXISTS venda_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, venda_id INTEGER, receita_id INTEGER, qtd INTEGER, FOREIGN KEY(venda_id) REFERENCES vendas(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS caixa (id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT, valor REAL, data_movimento TEXT, tipo TEXT, categoria TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orcamentos (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, data_emissao TEXT, validade TEXT, total REAL, itens_resumo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vendedoras (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS consignacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, vendedora_id INTEGER, receita_id INTEGER, qtd_entregue REAL, qtd_vendida REAL DEFAULT 0, data_entrega TEXT, FOREIGN KEY(vendedora_id) REFERENCES vendedoras(id), FOREIGN KEY(receita_id) REFERENCES receitas(id))''')
    conn.commit()
    return conn

conn = init_db()

# --- Funções Auxiliares ---
def limpar_sessao(keys):
    for key in keys:
        if key in st.session_state: del st.session_state[key]

def format_currency(value):
    return f"R$ {value:,.2f}"

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

# --- Interface Principal ---
st.title("🍰 Sagrado Doce - Gestão")

tab1, tab2, tab_estoque, tab_orc, tab3, tab4, tab_caixa = st.tabs([
    "📦 Insumos", "📒 Receitas", "📊 Estoque", "📑 Orçamentos", "🛒 Vendas", "📋 Produção", "💰 Financeiro"
])

# ==========================================
# ABA 1: INSUMOS
# ==========================================
with tab1:
    st.header("Cadastro de Insumos")
    col1, col2 = st.columns(2)
    with col1:
        nome_insumo = st.text_input("Nome", key="in_nome")
        unidade_tipo = st.selectbox("Unidade Uso", ["g (Gramas)", "mL (Mililitros)", "un (Unidade)"], key="in_unidade")
    with col2:
        custo_embalagem = st.number_input("Custo Embalagem (R$)", min_value=0.0, format="%.2f", value=None, key="in_custo")
        qtd_embalagem = st.number_input("Qtd Embalagem", min_value=0.0, format="%.2f", value=None, key="in_qtd")
        unidade_compra = st.selectbox("Unidade Compra", ["kg", "g", "L", "mL", "un"], key="in_un_compra")

    if st.button("Salvar Insumo"):
        if nome_insumo and custo_embalagem and qtd_embalagem:
            qtd_total_base = qtd_embalagem * 1000 if unidade_compra in ["kg", "L"] else qtd_embalagem
            custo_unitario_calc = custo_embalagem / qtd_total_base
            conn.execute("INSERT INTO insumos (nome, unidade_medida, custo_total, qtd_embalagem, fator_conversao, custo_unitario, estoque_atual) VALUES (?, ?, ?, ?, ?, ?, 0)",
                      (nome_insumo, unidade_tipo.split()[0], custo_embalagem, qtd_total_base, 1, custo_unitario_calc))
            conn.commit()
            st.success("Salvo!"); limpar_sessao(["in_nome", "in_custo", "in_qtd"]); st.rerun()
    
    st.divider()
    with st.expander("🗑️ Excluir Insumo"):
        insumos_del = pd.read_sql("SELECT id, nome FROM insumos", conn)
        if not insumos_del.empty:
            sel_del_ins = st.selectbox("Selecione para excluir:", insumos_del['nome'], key="sel_del_ins")
            if st.button("Excluir Insumo Selecionado"):
                id_del = insumos_del[insumos_del['nome'] == sel_del_ins]['id'].values[0]
                uso = pd.read_sql(f"SELECT COUNT(*) as count FROM receita_itens WHERE insumo_id={id_del}", conn).iloc[0]['count']
                if uso > 0: st.error(f"Insumo usado em {uso} receita(s). Não pode excluir.")
                else: conn.execute("DELETE FROM insumos WHERE id=?", (int(id_del),)); conn.commit(); st.success("Excluído!"); st.rerun()

    st.dataframe(pd.read_sql("SELECT nome, unidade_medida, custo_unitario FROM insumos", conn), use_container_width=True)

# ==========================================
# ABA 2: RECEITAS
# ==========================================
with tab2:
    st.header("Gerenciar Receitas")
    if 'ingredientes_temp' not in st.session_state: st.session_state.ingredientes_temp = []
    if 'editando_id' not in st.session_state: st.session_state.editando_id = None 
    
    receitas_existentes = pd.read_sql("SELECT id, nome FROM receitas", conn)
    modo_receita = st.radio("Ação:", ["Nova (Do Zero)", "Clonar/Escalar", "Editar Existente"], horizontal=True)

    if modo_receita in ["Clonar/Escalar", "Editar Existente"]:
        if not receitas_existentes.empty:
            sel_receita_nome = st.selectbox("Selecione a Receita", receitas_existentes['nome'])
            if st.button("Carregar Dados"):
                rec_id = receitas_existentes[receitas_existentes['nome'] == sel_receita_nome]['id'].values[0]
                rec_data = pd.read_sql(f"SELECT * FROM receitas WHERE id = {rec_id}", conn).iloc[0]
                itens_data = pd.read_sql(f"SELECT ri.insumo_id, i.nome, ri.qtd_usada, i.unidade_medida, i.custo_unitario FROM receita_itens ri JOIN insumos i ON ri.insumo_id = i.id WHERE ri.receita_id = {rec_id}", conn)
                st.session_state.ingredientes_temp = []
                for _, item in itens_data.iterrows():
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

    if st.session_state.ingredientes_temp and modo_receita == "Clonar/Escalar":
        with st.container(border=True):
            st.markdown("#### 📐 Escala")
            k1, k2, k3 = st.columns([1, 1, 1])
            fator = k1.number_input("Fator", min_value=1.0, value=1.0, step=0.5)
            if k2.button("➗ Dividir"):
                for item in st.session_state.ingredientes_temp: item['qtd'] /= fator; item['custo'] = item['qtd'] * item['custo_unitario']
                st.rerun()
            if k3.button("✖️ Multiplicar"):
                for item in st.session_state.ingredientes_temp: item['qtd'] *= fator; item['custo'] = item['qtd'] * item['custo_unitario']
                st.rerun()

    insumos_db = pd.read_sql("SELECT id, nome, unidade_medida, custo_unitario FROM insumos", conn)
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
                    existente = next((i for i in st.session_state.ingredientes_temp if i['nome'] == insumo_sel), None)
                    if existente: existente['qtd'] += qtd_add; existente['custo'] = existente['qtd'] * existente['custo_unitario']
                    else: st.session_state.ingredientes_temp.append({'id': int(dat['id']), 'nome': insumo_sel, 'qtd': qtd_add, 'unidade': dat['unidade_medida'], 'custo': qtd_add * dat['custo_unitario'], 'custo_unitario': dat['custo_unitario']})
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
                c = conn.cursor()
                if modo_receita == "Editar Existente" and st.session_state.editando_id:
                    c.execute("UPDATE receitas SET nome=?, preco_venda=?, custo_total=? WHERE id=?", (st.session_state.rec_nome_in, st.session_state.rec_venda_in, custo_total, st.session_state.editando_id))
                    c.execute("DELETE FROM receita_itens WHERE receita_id=?", (st.session_state.editando_id,))
                    final_id = st.session_state.editando_id; msg = "Receita Atualizada!"
                else:
                    c.execute("INSERT INTO receitas (nome, preco_venda, custo_total) VALUES (?, ?, ?)", (st.session_state.rec_nome_in, st.session_state.rec_venda_in, custo_total))
                    final_id = c.lastrowid; msg = "Nova Receita Criada!"
                for item in st.session_state.ingredientes_temp:
                    c.execute("INSERT INTO receita_itens (receita_id, insumo_id, qtd_usada, custo_item) VALUES (?, ?, ?, ?)", (final_id, item['id'], item['qtd'], item['custo']))
                conn.commit()
                st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
                limpar_sessao(['rec_nome_in', 'rec_venda_in', 'rec_qtd_add']); st.success(msg); st.rerun()
        
        with col_act2:
            if modo_receita == "Editar Existente" and st.session_state.editando_id:
                if st.button("❌ Excluir Receita", key="btn_del_rec"):
                    id_para_apagar = st.session_state.editando_id
                    c = conn.cursor()
                    c.execute("DELETE FROM receitas WHERE id=?", (id_para_apagar,))
                    c.execute("DELETE FROM receita_itens WHERE receita_id=?", (id_para_apagar,))
                    conn.commit()
                    st.session_state.ingredientes_temp = []; st.session_state.editando_id = None
                    limpar_sessao(['rec_nome_in', 'rec_venda_in'])
                    st.success("Receita Excluída com Sucesso!"); st.rerun()

# ==========================================
# ABA 3: ESTOQUE
# ==========================================
with tab_estoque:
    st.header("Estoque")
    c1, c2 = st.columns(2)
    with c1:
        insumos = pd.read_sql("SELECT id, nome, unidade_medida FROM insumos", conn)
        if not insumos.empty:
            sel = st.selectbox("Insumo", insumos['nome'], key="stk_sel")
            qtd = st.number_input("Qtd Adicionar (Negativo reduz)", step=1.0, key="stk_qtd")
            if st.button("Atualizar Estoque"):
                iid = insumos[insumos['nome'] == sel]['id'].values[0]
                conn.execute("UPDATE insumos SET estoque_atual = estoque_atual + ? WHERE id = ?", (qtd, int(iid)))
                conn.commit(); st.success("Ok!"); st.rerun()
    with c2:
        st.dataframe(pd.read_sql("SELECT nome, estoque_atual, unidade_medida FROM insumos", conn), use_container_width=True)

# ==========================================
# ABA 4: ORÇAMENTOS (ATUALIZADO COM DESCONTO)
# ==========================================
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
            receitas_orc = pd.read_sql("SELECT id, nome, preco_venda, custo_total FROM receitas", conn)
            if not receitas_orc.empty:
                co1, co2, co3 = st.columns([2, 1, 1])
                prod_orc = co1.selectbox("Produto", receitas_orc['nome'], key="orc_prod")
                qtd_orc = co2.number_input("Qtd", min_value=1, value=1, key="orc_qtd")
                d_orc = receitas_orc[receitas_orc['nome'] == prod_orc].iloc[0]
                if co3.button("Add"):
                    st.session_state.carrinho_orc.append({'produto': prod_orc, 'qtd': qtd_orc, 'unitario': d_orc['preco_venda'], 'custo_unit': d_orc['custo_total'], 'total': qtd_orc * d_orc['preco_venda']})
                    st.rerun()
        else:
            ca1, ca2, ca3 = st.columns(3)
            nome_avulso = ca1.text_input("Descrição do Item")
            custo_avulso = ca2.number_input("Custo Interno (R$)", min_value=0.0)
            preco_avulso = ca3.number_input("Preço de Venda (R$)", min_value=0.0)
            if st.button("Add Avulso"):
                if nome_avulso and preco_avulso:
                    st.session_state.carrinho_orc.append({'produto': nome_avulso, 'qtd': 1, 'unitario': preco_avulso, 'custo_unit': custo_avulso, 'total': preco_avulso})
                    st.rerun()
                
    if st.session_state.carrinho_orc:
        st.divider()
        st.markdown("### Visão Interna")
        df_orc = pd.DataFrame(st.session_state.carrinho_orc)
        df_orc['Custo Total'] = df_orc['custo_unit'] * df_orc['qtd']
        df_orc['Lucro Est.'] = df_orc['total'] - df_orc['Custo Total']
        st.dataframe(df_orc[['produto', 'qtd', 'unitario', 'total', 'Custo Total', 'Lucro Est.']], use_container_width=True)
        
        total_original = df_orc['total'].sum()
        
        # --- ÁREA DE DESCONTO E TOTALIZADORES ---
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown(f"**Total Original: {format_currency(total_original)}**")
            
            # Input do valor desejado
            valor_final_desejado = st.number_input("Valor Final com Desconto (R$)", value=total_original, step=1.0)
            
            # Cálculo
            desconto_reais = total_original - valor_final_desejado
            desconto_perc = 0
            if total_original > 0:
                desconto_perc = (desconto_reais / total_original) * 100
                
            if desconto_reais > 0:
                st.caption(f"🔻 Desconto aplicado: {format_currency(desconto_reais)} ({desconto_perc:.1f}%)")
            
        with col_t2:
            st.metric("Total Final para Cliente", format_currency(valor_final_desejado))

        c_a1, c_a2 = st.columns(2)
        if c_a1.button("Limpar Orçamento"): st.session_state.carrinho_orc = []; st.rerun()
        
        if c_a2.button("📄 Gerar Folha do Cliente"):
            hoje = datetime.now().strftime("%d/%m/%Y")
            img_b64 = get_base64_image("logo.png") 
            logo_html = f'<div class="logo-container"><img src="data:image/png;base64,{img_b64}" class="logo-img"></div>' if img_b64 else '<div class="logo-container" style="font-size:40px">🍰</div>'
            itens_html = "".join([f"<tr><td>{i['produto']}</td><td>{i['qtd']}</td><td>{format_currency(i['unitario'])}</td><td>{format_currency(i['total'])}</td></tr>" for i in st.session_state.carrinho_orc])
            
            # HTML Lógica do Desconto
            if desconto_reais > 0:
                footer_table = f"""
                <tr>
                    <td colspan="3" class="subtotal-row">Subtotal:</td>
                    <td style="text-align: right;">{format_currency(total_original)}</td>
                </tr>
                <tr>
                    <td colspan="3" class="subtotal-row" style="color: red;">Desconto ({desconto_perc:.1f}%):</td>
                    <td style="text-align: right; color: red;">- {format_currency(desconto_reais)}</td>
                </tr>
                <tr class="total-row">
                    <td colspan="3" style="text-align: right;">Total Final:</td>
                    <td>{format_currency(valor_final_desejado)}</td>
                </tr>
                """
            else:
                footer_table = f"""
                <tr class="total-row">
                    <td colspan="3" style="text-align: right;">Total:</td>
                    <td>{format_currency(total_original)}</td>
                </tr>
                """

            html = f"""<div class="invoice-box"><div class="header-top">{logo_html}<div class="header-title">Sagrado Doce</div></div><div style="margin:20px 0"><strong>Cliente:</strong> {orc_cliente}<br><strong>Data:</strong> {hoje}<br><strong>Validade:</strong> {orc_validade}</div><table class="table-custom"><tr class="heading"><th>Item</th><th>Qtd</th><th>Unit.</th><th>Total</th></tr>{itens_html}{footer_table}</table><div style="margin-top:40px; text-align:center; font-size:12px; color:#aaa;">Obrigado pela preferência!</div></div>"""
            st.markdown(html, unsafe_allow_html=True)

# ==========================================
# ABA 5: VENDAS
# ==========================================
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
        receitas = pd.read_sql("SELECT id, nome, preco_venda FROM receitas", conn)
        if not receitas.empty:
            prod = st.selectbox("Produto", receitas['nome'], key="v_prod")
            d_prod = receitas[receitas['nome'] == prod].iloc[0]
            qv = st.number_input("Qtd", min_value=1, key="v_qtd")
            
            if 'carrinho' not in st.session_state: st.session_state.carrinho = []
            if st.button("Add Carrinho", key="add_venda"):
                st.session_state.carrinho.append({'id': int(d_prod['id']), 'produto': prod, 'qtd': qv, 'total': qv * d_prod['preco_venda']})
                st.rerun()

            if st.session_state.carrinho:
                df_c = pd.DataFrame(st.session_state.carrinho)
                st.dataframe(df_c[['qtd', 'produto', 'total']], use_container_width=True)
                tot = df_c['total'].sum()
                st.metric("Total", format_currency(tot))
                if st.button("✅ Confirmar Pedido", key="conf_venda"):
                    resumo = "; ".join([f"{x['qtd']}x {x['produto']}" for x in st.session_state.carrinho])
                    c = conn.cursor()
                    c.execute("INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, 'Pendente')", (cli, tipo, end, pagto, resumo, tot, 'Em Produção'))
                    vid = c.lastrowid
                    for i in st.session_state.carrinho: c.execute("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (?, ?, ?)", (vid, i['id'], i['qtd']))
                    conn.commit(); st.session_state.carrinho = []; limpar_sessao(['v_cli', 'v_end']); st.success("Pedido Feito!"); st.rerun()

    with sub_tab_vendedoras:
        col_vend1, col_vend2 = st.columns([1, 2])
        with col_vend1:
            st.subheader("Vendedora")
            novo_nome_vend = st.text_input("Cadastrar Nova Vendedora")
            if st.button("Cadastrar"):
                if novo_nome_vend: conn.execute("INSERT INTO vendedoras (nome) VALUES (?)", (novo_nome_vend,)); conn.commit(); st.success("Cadastrada!"); st.rerun()
            st.divider()
            vendedoras_db = pd.read_sql("SELECT * FROM vendedoras", conn)
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
                            conn.execute("INSERT INTO consignacoes (vendedora_id, receita_id, qtd_entregue, data_entrega) VALUES (?, ?, ?, datetime('now'))", (int(vendedora_id), int(id_prod_entregar), qtd_entregar))
                            conn.commit(); st.success(f"Entregue {qtd_entregar}x {prod_entregar}"); st.rerun()
            else: st.warning("Cadastre uma vendedora.")

        with col_vend2:
            if not vendedoras_db.empty:
                st.subheader(f"Sacola de {vendedora_sel_nome}")
                query_sacola = f"SELECT c.id, r.nome, c.qtd_entregue, c.qtd_vendida, (c.qtd_entregue - c.qtd_vendida) as em_maos, r.preco_venda, r.id as rec_id FROM consignacoes c JOIN receitas r ON c.receita_id = r.id WHERE c.vendedora_id = {vendedora_id} AND (c.qtd_entregue - c.qtd_vendida) > 0"
                sacola = pd.read_sql(query_sacola, conn)
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
                            c = conn.cursor()
                            c.execute("UPDATE consignacoes SET qtd_vendida = qtd_vendida + ? WHERE id = ?", (qtd_venda_vend, id_consignacao))
                            resumo_venda = f"{qtd_venda_vend}x {dados_item['nome']} (Via {vendedora_sel_nome})"
                            if desconto_un > 0: resumo_venda += f" [Desc: R${desconto_un}/un]"
                            status_pg = 'Pago' if receber_agora else 'Pendente'
                            c.execute('''INSERT INTO vendas (cliente, data_pedido, tipo_entrega, endereco, forma_pagamento, itens_resumo, total_venda, status, status_pagamento) VALUES (?, datetime('now'), 'Venda Externa', ?, ?, ?, ?, 'Concluído', ?)''', (f"Vend. {vendedora_sel_nome}", "N/A", pagto_vend, resumo_venda, total_venda_vend, status_pg))
                            vid = c.lastrowid
                            c.execute("INSERT INTO venda_itens (venda_id, receita_id, qtd) VALUES (?, ?, ?)", (vid, int(dados_item['rec_id']), qtd_venda_vend))
                            if receber_agora: c.execute("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (?, ?, datetime('now'), 'Entrada', 'Vendas')", (f"Venda #{vid} - {vendedora_sel_nome}", total_venda_vend))
                            conn.commit(); st.success("Venda Registrada!"); st.rerun()
                else: st.info("Ela não tem produtos em mãos.")

# ==========================================
# ABA 6: PRODUÇÃO
# ==========================================
with tab4:
    st.header("Produção")
    st_filtro = st.radio("Ver", ["Em Produção", "Concluídos"], horizontal=True)
    st_db = "Em Produção" if st_filtro == "Em Produção" else "Concluído"
    df = pd.read_sql(f"SELECT * FROM vendas WHERE status = '{st_db}' ORDER BY id DESC", conn)
    if not df.empty:
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**#{r['id']} {r['cliente']}**"); c1.text(r['itens_resumo'])
                status_pag = "🔴 Pendente" if r['status_pagamento'] == "Pendente" else "🟢 Pago"
                c2.text(f"{r['tipo_entrega']} | {r['forma_pagamento']}"); c2.markdown(f"**{status_pag}**")
                if r['status'] == "Em Produção":
                    if c3.button("Finalizar Produção", key=f"f_{r['id']}"):
                        conn.execute("UPDATE vendas SET status='Concluído' WHERE id=?", (r['id'],)); conn.commit(); st.rerun()
                with c3.expander("Opções"):
                     if st.button("🗑️ Excluir Pedido", key=f"del_v_{r['id']}"):
                         conn.execute("DELETE FROM vendas WHERE id=?", (r['id'],)); conn.execute("DELETE FROM venda_itens WHERE venda_id=?", (r['id'],)); conn.commit(); st.warning("Excluído"); st.rerun()
    else: st.info("Sem pedidos.")

# ==========================================
# ABA 7: CAIXA
# ==========================================
with tab_caixa:
    st.header("Financeiro")
    st.subheader("Pendentes")
    pend = pd.read_sql("SELECT id, cliente, total_venda FROM vendas WHERE status_pagamento = 'Pendente'", conn)
    if not pend.empty:
        for _, r in pend.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"#{r['id']} {r['cliente']} - {format_currency(r['total_venda'])}")
                if c2.button("Receber", key=f"rec_{r['id']}"):
                    conn.execute("UPDATE vendas SET status_pagamento='Pago' WHERE id=?", (r['id'],)); conn.execute("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (?, ?, datetime('now'), 'Entrada', 'Vendas')", (f"Venda #{r['id']}", r['total_venda'])); conn.commit(); st.rerun()
    else: st.info("Tudo pago.")
    
    st.divider()
    with st.expander("Lançamento Manual"):
        l1, l2, l3 = st.columns(3)
        tp = l1.radio("Tipo", ["Saída", "Entrada"]); desc = l2.text_input("Desc"); val = l2.number_input("Valor")
        cat = l3.selectbox("Cat", ["Contas", "Insumos", "Outros"])
        if l3.button("Lançar"): conn.execute("INSERT INTO caixa (descricao, valor, data_movimento, tipo, categoria) VALUES (?, ?, datetime('now'), ?, ?)", (desc, val, tp, cat)); conn.commit(); st.rerun()
    
    cx = pd.read_sql("SELECT * FROM caixa ORDER BY id DESC", conn)
    if not cx.empty:
        ent = cx[cx['tipo']=='Entrada']['valor'].sum(); sai = cx[cx['tipo']=='Saída']['valor'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", format_currency(ent)); c2.metric("Saídas", format_currency(sai)); c3.metric("Saldo", format_currency(ent-sai))
        with st.expander("Gerenciar Lançamentos (Excluir)"):
            sel_cx_id = st.selectbox("Selecione ID para excluir:", cx['id'].astype(str) + " - " + cx['descricao'])
            if st.button("Excluir Lançamento Selecionado"):
                id_to_del = int(sel_cx_id.split(" - ")[0]); conn.execute("DELETE FROM caixa WHERE id=?", (id_to_del,)); conn.commit(); st.success("Excluído!"); st.rerun()
        st.dataframe(cx, use_container_width=True)

# --- Sidebar ---
with st.sidebar:
    st.info("ℹ️ Para usar logo: Salve arquivo 'logo.png' na pasta do app.")
    if st.button("🗑️ Resetar Tudo") and st.button("Confirmar Reset"):
        for t in ["venda_itens", "vendas", "receita_itens", "receitas", "insumos", "caixa", "orcamentos", "vendedoras", "consignacoes"]: conn.execute(f"DELETE FROM {t}"); conn.execute("DELETE FROM sqlite_sequence")
        conn.commit(); st.session_state.clear(); st.rerun()

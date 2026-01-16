import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import base64
import os
import time

# --- Configuração da Página ---
st.set_page_config(page_title="Sagrado Doce", layout="wide", page_icon="🍰")

# --- CSS para Mobile (Botões Grandes) ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { border-radius: 8px; }
    .stSelectbox>div>div>div { border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE BANCO DE DADOS (CORE) ---
def get_data(worksheet, ttl=0):
    """Lê os dados da aba e garante que não venha vazio"""
    try:
        df = conn.read(worksheet=worksheet, ttl=ttl)
        return df if not df.empty else pd.DataFrame()
    except:
        return pd.DataFrame()

def save_data(df, worksheet):
    """Salva os dados e limpa o cache"""
    conn.update(worksheet=worksheet, data=df)
    st.cache_data.clear()

def get_next_id(df):
    """Gera o próximo ID (Simula Auto-Incremento)"""
    if df.empty or 'id' not in df.columns:
        return 1
    # Garante que a coluna id é numérica
    df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0)
    return int(df['id'].max()) + 1

# --- FUNÇÕES AUXILIARES ---
def format_currency(value):
    return f"R$ {float(value):,.2f}"

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode()
    return None

def limpar_sessao(keys): 
    for k in keys: 
        if k in st.session_state: del st.session_state[k]

# --- APP ---
st.title("🍰 Sagrado Doce")

# Abas iguais ao original
tab1, tab2, tab_estoque, tab_orc, tab3, tab4, tab_caixa = st.tabs([
    "📦 Insumos", "📒 Receitas", "📊 Estoque", "📑 Orçamentos", "🛒 Vendas", "📋 Produção", "💰 Caixa"
])

# ================= ABA 1: INSUMOS =================
with tab1:
    st.header("Insumos")
    
    # Leitura
    df_insumos = get_data("Insumos")
    
    with st.form("form_insumo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome")
        unidade = c1.selectbox("Unidade Uso", ["g", "mL", "un"])
        custo = c2.number_input("Custo Emb. (R$)", min_value=0.0)
        qtd_emb = c2.number_input("Qtd Emb.", min_value=0.0)
        un_compra = c2.selectbox("Unidade Compra", ["kg", "L", "un", "g", "mL"])
        
        if st.form_submit_button("💾 Salvar"):
            if nome and custo and qtd_emb:
                # Calculo
                qtd_total = qtd_emb * 1000 if un_compra in ["kg", "L"] else qtd_emb
                custo_un = custo / qtd_total if qtd_total > 0 else 0
                
                # Novo ID
                next_id = get_next_id(df_insumos)
                
                novo_dado = pd.DataFrame([{
                    "id": next_id, "nome": nome, "unidade_medida": unidade, 
                    "custo_total": custo, "qtd_embalagem": qtd_total, 
                    "custo_unitario": custo_un, "estoque_atual": 0
                }])
                
                df_final = pd.concat([df_insumos, novo_dado], ignore_index=True)
                save_data(df_final, "Insumos")
                st.success("Salvo!")
                st.rerun()

    if not df_insumos.empty:
        st.dataframe(df_insumos[['id', 'nome', 'estoque_atual', 'unidade_medida']], use_container_width=True)
        
        # Excluir (Fora do form para ser rapido)
        with st.expander("Excluir Insumo"):
            ing_del = st.selectbox("Selecionar", df_insumos['nome'].unique())
            if st.button("🗑️ Deletar"):
                df_insumos = df_insumos[df_insumos['nome'] != ing_del]
                save_data(df_insumos, "Insumos")
                st.rerun()

# ================= ABA 2: RECEITAS =================
with tab2:
    st.header("Receitas")
    
    # Estados de sessão para receita
    if 'temp_ingredientes' not in st.session_state: st.session_state.temp_ingredientes = []
    
    df_receitas = get_data("Receitas")
    df_insumos = get_data("Insumos")
    
    # 1. Cabeçalho da Receita
    with st.form("form_receita_header"):
        st.subheader("Nova / Editar Receita")
        nome_rec = st.text_input("Nome da Receita")
        preco_rec = st.number_input("Preço Venda", min_value=0.0)
        
        # Adicionar Insumo à lista temporária
        c1, c2, c3 = st.columns([2, 1, 1])
        if not df_insumos.empty:
            ing_sel = c1.selectbox("Ingrediente", df_insumos['nome'].unique())
            qtd_ing = c2.number_input("Qtd", min_value=0.0)
            add_ing = c3.form_submit_button("➕ Add Item")
            
            if add_ing and qtd_ing > 0:
                # Pega dados do insumo
                dados_insumo = df_insumos[df_insumos['nome'] == ing_sel].iloc[0]
                custo_calc = qtd_ing * dados_insumo['custo_unitario']
                st.session_state.temp_ingredientes.append({
                    "insumo_id": dados_insumo['id'],
                    "nome": ing_sel,
                    "qtd": qtd_ing,
                    "unidade": dados_insumo['unidade_medida'],
                    "custo": custo_calc
                })
                st.toast("Item adicionado!")

        # Visualizar lista temporária dentro do form (workaround)
        st.write("---")
        st.write("Itens adicionados:")
        custo_total_rec = 0
        for item in st.session_state.temp_ingredientes:
            st.text(f"- {item['qtd']}{item['unidade']} de {item['nome']} (R$ {item['custo']:.2f})")
            custo_total_rec += item['custo']
            
        st.info(f"Custo Total: {format_currency(custo_total_rec)}")

        # Salvar Tudo
        salvar_rec = st.form_submit_button("💾 SALVAR RECEITA COMPLETA")
        
        if salvar_rec and nome_rec:
            # 1. Salvar Receita (Pai)
            rec_id = get_next_id(df_receitas)
            nova_rec = pd.DataFrame([{
                "id": rec_id, "nome": nome_rec, 
                "preco_venda": preco_rec, "custo_total": custo_total_rec
            }])
            df_receitas = pd.concat([df_receitas, nova_rec], ignore_index=True)
            save_data(df_receitas, "Receitas")
            
            # 2. Salvar Itens (Filhos)
            df_rec_itens = get_data("Receita_Itens")
            next_item_id = get_next_id(df_rec_itens)
            
            novos_itens = []
            for item in st.session_state.temp_ingredientes:
                novos_itens.append({
                    "id": next_item_id,
                    "receita_id": rec_id,
                    "insumo_id": item['insumo_id'],
                    "qtd_usada": item['qtd'],
                    "custo_item": item['custo']
                })
                next_item_id += 1
            
            if novos_itens:
                df_rec_itens = pd.concat([df_rec_itens, pd.DataFrame(novos_itens)], ignore_index=True)
                save_data(df_rec_itens, "Receita_Itens")
            
            st.session_state.temp_ingredientes = []
            st.success("Receita criada com sucesso!")
            st.rerun()

# ================= ABA 3: ESTOQUE =================
with tab_estoque:
    st.header("Movimentação de Estoque")
    df_insumos = get_data("Insumos")
    
    if not df_insumos.empty:
        with st.form("att_estoque"):
            c1, c2 = st.columns(2)
            insumo_up = c1.selectbox("Insumo", df_insumos['nome'].unique())
            qtd_up = c2.number_input("Qtd Entrada/Saída (+/-)", step=1.0)
            
            if st.form_submit_button("Atualizar"):
                idx = df_insumos.index[df_insumos['nome'] == insumo_up].tolist()[0]
                # Converte para float para garantir cálculo
                atual = float(df_insumos.at[idx, 'estoque_atual'])
                df_insumos.at[idx, 'estoque_atual'] = atual + qtd_up
                save_data(df_insumos, "Insumos")
                st.success("Atualizado!")
                st.rerun()
                
        st.dataframe(df_insumos[['nome', 'estoque_atual', 'unidade_medida']], use_container_width=True)

# ================= ABA 4: ORÇAMENTOS =================
with tab_orc:
    st.header("Simulador de Orçamento")
    # Aqui usamos session state simples, sem salvar no banco para não poluir
    if 'cart_orc' not in st.session_state: st.session_state.cart_orc = []
    
    df_receitas = get_data("Receitas")
    
    c1, c2 = st.columns([2, 1])
    cli_orc = c1.text_input("Cliente Orc.")
    
    if not df_receitas.empty:
        prod_orc = st.selectbox("Produto", df_receitas['nome'].unique(), key="sb_orc")
        if st.button("Adicionar ao Orçamento"):
             dados = df_receitas[df_receitas['nome'] == prod_orc].iloc[0]
             st.session_state.cart_orc.append({
                 "Produto": prod_orc,
                 "Preço": float(dados['preco_venda'])
             })
             
    if st.session_state.cart_orc:
        df_cart = pd.DataFrame(st.session_state.cart_orc)
        st.dataframe(df_cart, use_container_width=True)
        total = df_cart['Preço'].sum()
        st.metric("Total Estimado", format_currency(total))
        if st.button("Limpar Orçamento"):
            st.session_state.cart_orc = []
            st.rerun()

# ================= ABA 5: VENDAS =================
with tab3:
    st.header("Vendas")
    sub1, sub2 = st.tabs(["Balcão", "Vendedoras/Consignado"])
    
    # --- BALCÃO ---
    with sub1:
        if 'carrinho_venda' not in st.session_state: st.session_state.carrinho_venda = []
        
        df_receitas = get_data("Receitas")
        
        with st.form("form_venda"):
            c1, c2 = st.columns(2)
            cli = c1.text_input("Cliente")
            pgto = c2.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"])
            
            st.divider()
            if not df_receitas.empty:
                prod = st.selectbox("Produto", df_receitas['nome'].unique())
                qtd = st.number_input("Qtd", min_value=1, value=1)
                
                # Botão Add Carrinho (Lógica interna do form)
                add_btn = st.form_submit_button("➕ Adicionar ao Carrinho")
                if add_btn:
                    dados = df_receitas[df_receitas['nome'] == prod].iloc[0]
                    st.session_state.carrinho_venda.append({
                        "id": dados['id'],
                        "nome": prod,
                        "qtd": qtd,
                        "total": qtd * float(dados['preco_venda'])
                    })
                    st.toast("Adicionado!")

        # Visualizar Carrinho e Fechar (Fora do form para ver atualização)
        if st.session_state.carrinho_venda:
            st.write("### Carrinho:")
            df_c = pd.DataFrame(st.session_state.carrinho_venda)
            st.dataframe(df_c, use_container_width=True)
            total_venda = df_c['total'].sum()
            st.metric("Total", format_currency(total_venda))
            
            c_act1, c_act2 = st.columns(2)
            if c_act1.button("✅ FINALIZAR VENDA"):
                with st.spinner("Salvando venda..."):
                    # 1. Salvar Venda
                    df_vendas = get_data("Vendas")
                    venda_id = get_next_id(df_vendas)
                    resumo = ", ".join([f"{i['qtd']}x {i['nome']}" for i in st.session_state.carrinho_venda])
                    
                    nova_venda = pd.DataFrame([{
                        "id": venda_id, "cliente": cli, "data_pedido": datetime.now().strftime("%Y-%m-%d"),
                        "forma_pagamento": pgto, "itens_resumo": resumo, 
                        "total_venda": total_venda, "status": "Em Produção", "status_pagamento": "Pendente"
                    }])
                    df_vendas = pd.concat([df_vendas, nova_venda], ignore_index=True)
                    save_data(df_vendas, "Vendas")
                    
                    # 2. Salvar Itens
                    df_v_itens = get_data("Venda_Itens")
                    next_vi_id = get_next_id(df_v_itens)
                    lista_vi = []
                    for item in st.session_state.carrinho_venda:
                        lista_vi.append({
                            "id": next_vi_id, "venda_id": venda_id, 
                            "receita_id": item['id'], "qtd": item['qtd']
                        })
                        next_vi_id += 1
                    save_data(pd.concat([df_v_itens, pd.DataFrame(lista_vi)], ignore_index=True), "Venda_Itens")
                    
                    st.session_state.carrinho_venda = []
                    st.success("Venda Realizada!")
                    st.rerun()

            if c_act2.button("Limpar Carrinho"):
                st.session_state.carrinho_venda = []
                st.rerun()

    # --- VENDEDORAS ---
    with sub2:
        df_vendedoras = get_data("Vendedoras")
        
        with st.expander("Cadastrar Vendedora"):
            with st.form("cad_vend"):
                n_vend = st.text_input("Nome")
                if st.form_submit_button("Cadastrar"):
                    nid = get_next_id(df_vendedoras)
                    nv = pd.DataFrame([{"id": nid, "nome": n_vend}])
                    save_data(pd.concat([df_vendedoras, nv], ignore_index=True), "Vendedoras")
                    st.rerun()
        
        if not df_vendedoras.empty:
            sel_vend = st.selectbox("Selecionar Vendedora", df_vendedoras['nome'].unique())
            vend_id = df_vendedoras[df_vendedoras['nome'] == sel_vend]['id'].values[0]
            
            # Entregar Sacola
            st.write("---")
            st.write("👜 **Entregar Sacola**")
            with st.form("entregar_sacola"):
                if not df_receitas.empty:
                    p_sacola = st.selectbox("Produto", df_receitas['nome'].unique())
                    q_sacola = st.number_input("Qtd", min_value=1)
                    if st.form_submit_button("Entregar"):
                        df_consig = get_data("Consignacoes")
                        rec_id = df_receitas[df_receitas['nome'] == p_sacola]['id'].values[0]
                        nc_id = get_next_id(df_consig)
                        
                        novo_consig = pd.DataFrame([{
                            "id": nc_id, "vendedora_id": vend_id, "receita_id": rec_id,
                            "qtd_entregue": q_sacola, "qtd_vendida": 0, 
                            "data_entrega": datetime.now().strftime("%Y-%m-%d")
                        }])
                        save_data(pd.concat([df_consig, novo_consig], ignore_index=True), "Consignacoes")
                        st.success("Entregue!")
            
            # Visualizar Sacola
            df_consig = get_data("Consignacoes")
            if not df_consig.empty:
                # Merge para pegar nomes
                minha_sacola = df_consig[df_consig['vendedora_id'] == vend_id].copy()
                if not minha_sacola.empty:
                    # Ajuste de tipos para merge
                    minha_sacola['receita_id'] = minha_sacola['receita_id'].astype(int)
                    df_receitas['id'] = df_receitas['id'].astype(int)
                    
                    full_view = pd.merge(minha_sacola, df_receitas[['id','nome','preco_venda']], left_on='receita_id', right_on='id')
                    full_view['Em Mãos'] = full_view['qtd_entregue'] - full_view['qtd_vendida']
                    full_view = full_view[full_view['Em Mãos'] > 0] # Só mostra o que tem
                    
                    st.dataframe(full_view[['nome', 'qtd_entregue', 'qtd_vendida', 'Em Mãos']], use_container_width=True)
                    
                    st.write("📉 **Baixa (Venda)**")
                    with st.form("baixa_vend"):
                        item_baixa = st.selectbox("Item", full_view['nome'].unique())
                        qtd_bx = st.number_input("Qtd Vendida", min_value=1)
                        if st.form_submit_button("Registrar Venda"):
                            # Achar ID da consignacao
                            row = full_view[full_view['nome'] == item_baixa].iloc[0]
                            consig_id = row['id_x'] # id da tabela consignacoes
                            
                            # Atualizar Consignacao
                            idx_consig = df_consig.index[df_consig['id'] == consig_id].tolist()[0]
                            df_consig.at[idx_consig, 'qtd_vendida'] += qtd_bx
                            save_data(df_consig, "Consignacoes")
                            
                            # Gerar Venda e Caixa
                            total = qtd_bx * float(row['preco_venda'])
                            
                            # Salvar Venda Simples
                            df_vendas = get_data("Vendas")
                            nv = pd.DataFrame([{
                                "id": get_next_id(df_vendas), "cliente": f"Vend. {sel_vend}",
                                "data_pedido": datetime.now().strftime("%Y-%m-%d"),
                                "total_venda": total, "status": "Concluído", "status_pagamento": "Pago"
                            }])
                            save_data(pd.concat([df_vendas, nv], ignore_index=True), "Vendas")
                            
                            # Salvar Caixa
                            df_caixa = get_data("Caixa")
                            nc = pd.DataFrame([{
                                "id": get_next_id(df_caixa), "data": datetime.now().strftime("%Y-%m-%d"),
                                "descricao": f"Venda {sel_vend} - {item_baixa}", "valor": total,
                                "tipo": "Entrada", "categoria": "Vendas"
                            }])
                            save_data(pd.concat([df_caixa, nc], ignore_index=True), "Caixa")
                            
                            st.success("Baixa realizada e Caixa atualizado!")
                            st.rerun()

# ================= ABA 6: PRODUÇÃO =================
with tab4:
    st.header("Produção")
    df_vendas = get_data("Vendas")
    if not df_vendas.empty:
        # Filtro
        em_prod = df_vendas[df_vendas['status'] == 'Em Produção']
        if not em_prod.empty:
            for i, row in em_prod.iterrows():
                with st.expander(f"Pedido #{row['id']} - {row['cliente']}"):
                    st.write(row['itens_resumo'])
                    if st.button("✅ Concluir", key=f"conc_{row['id']}"):
                        idx = df_vendas.index[df_vendas['id'] == row['id']].tolist()[0]
                        df_vendas.at[idx, 'status'] = "Concluído"
                        save_data(df_vendas, "Vendas")
                        st.rerun()
        else:
            st.info("Nenhum pedido em produção.")

# ================= ABA 7: FINANCEIRO =================
with tab_caixa:
    st.header("Financeiro")
    df_caixa = get_data("Caixa")
    
    # Pendentes (Vendas não pagas)
    df_vendas = get_data("Vendas")
    if not df_vendas.empty:
        pendentes = df_vendas[df_vendas['status_pagamento'] == 'Pendente']
        if not pendentes.empty:
            st.warning(f"Você tem {len(pendentes)} pedidos a receber.")
            pg_id = st.selectbox("Receber Pedido", pendentes['id'].astype(str) + " - " + pendentes['cliente'])
            if st.button("💰 Receber"):
                pid = int(pg_id.split(" - ")[0])
                idx = df_vendas.index[df_vendas['id'] == pid].tolist()[0]
                val = df_vendas.at[idx, 'total_venda']
                
                # Atualiza Venda
                df_vendas.at[idx, 'status_pagamento'] = "Pago"
                save_data(df_vendas, "Vendas")
                
                # Lança Caixa
                nc = pd.DataFrame([{
                    "id": get_next_id(df_caixa), "data": datetime.now().strftime("%Y-%m-%d"),
                    "descricao": f"Receb. Pedido #{pid}", "valor": val,
                    "tipo": "Entrada", "categoria": "Vendas"
                }])
                save_data(pd.concat([df_caixa, nc], ignore_index=True), "Caixa")
                st.rerun()
    
    st.divider()
    
    # Lançamento Manual
    with st.form("lanca_caixa"):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição")
        val = c2.number_input("Valor", min_value=0.0)
        tipo = c3.radio("Tipo", ["Entrada", "Saída"])
        
        if st.form_submit_button("Lançar"):
            nc = pd.DataFrame([{
                "id": get_next_id(df_caixa), "data": datetime.now().strftime("%Y-%m-%d"),
                "descricao": desc, "valor": val,
                "tipo": tipo, "categoria": "Manual"
            }])
            save_data(pd.concat([df_caixa, nc], ignore_index=True), "Caixa")
            st.rerun()
            
    # Extrato
    if not df_caixa.empty:
        # Converter para numeros
        df_caixa['valor'] = pd.to_numeric(df_caixa['valor'])
        ent = df_caixa[df_caixa['tipo'] == 'Entrada']['valor'].sum()
        sai = df_caixa[df_caixa['tipo'] == 'Saída']['valor'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", format_currency(ent))
        c2.metric("Saídas", format_currency(sai))
        c3.metric("Saldo", format_currency(ent - sai))
        
        st.dataframe(df_caixa.sort_values(by='id', ascending=False), use_container_width=True)

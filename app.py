import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(page_title="Sagrado Doce", layout="wide", page_icon="🍰")

# --- CSS para melhorar visual no Celular ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; }
    .stTextInput>div>div>input { border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🍰 Sagrado Doce")

# --- CONEXÃO COM GOOGLE SHEETS ---
# Crie a conexão. No Streamlit Cloud, você vai configurar o link da planilha nos Secrets.
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE DADOS (Simples e Rápidas) ---
def carregar_dados(aba):
    # TTL=0 garante que ele sempre pegue o dado mais novo se alguém mudou lá na planilha
    return conn.read(worksheet=aba, ttl=0)

def salvar_dados(df_novo, aba):
    conn.update(worksheet=aba, data=df_novo)
    st.cache_data.clear() # Limpa cache para ver a mudança

# --- ABAS DO APP ---
tab1, tab2, tab3 = st.tabs(["🛒 Venda", "📦 Estoque", "💰 Caixa"])

# ==========================================
# ABA 1: VENDAS (Foco em Rapidez no Celular)
# ==========================================
with tab1:
    st.header("Nova Venda")
    
    # Carrega dados necessários
    df_receitas = carregar_dados("Receitas") # Precisa ter colunas: Nome, Preco
    lista_produtos = df_receitas['Nome'].tolist() if not df_receitas.empty else []
    
    # FORMULÁRIO (Essencial para não travar no celular)
    with st.form("form_venda"):
        col1, col2 = st.columns(2)
        cliente = col1.text_input("Cliente")
        pagto = col2.selectbox("Pagamento", ["Pix", "Dinheiro", "Cartão"])
        
        st.divider()
        st.markdown("### Itens")
        produto_sel = st.selectbox("Produto", lista_produtos)
        qtd = st.number_input("Quantidade", min_value=1, value=1)
        
        # Botão Grande de Enviar
        enviar = st.form_submit_button("✅ Finalizar Venda")
        
        if enviar:
            # 1. Calcular Valor
            preco_item = df_receitas[df_receitas['Nome'] == produto_sel]['Preco'].values[0]
            total = preco_item * qtd
            
            # 2. Salvar na aba Vendas
            df_vendas = carregar_dados("Vendas")
            nova_venda = pd.DataFrame([{
                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "Cliente": cliente,
                "Produto": produto_sel,
                "Qtd": qtd,
                "Total": total,
                "Pagamento": pagto
            }])
            df_vendas_atualizado = pd.concat([df_vendas, nova_venda], ignore_index=True)
            salvar_dados(df_vendas_atualizado, "Vendas")
            
            # 3. Salvar no Caixa
            df_caixa = carregar_dados("Caixa")
            novo_caixa = pd.DataFrame([{
                "Data": datetime.now().strftime("%d/%m/%Y"),
                "Descricao": f"Venda {cliente}",
                "Entrada": total,
                "Saida": 0
            }])
            df_caixa_atualizado = pd.concat([df_caixa, novo_caixa], ignore_index=True)
            salvar_dados(df_caixa_atualizado, "Caixa")
            
            st.success(f"Venda de R$ {total:.2f} registrada!")

# ==========================================
# ABA 2: ESTOQUE (Insumos)
# ==========================================
with tab2:
    st.header("Estoque de Insumos")
    
    df_insumos = carregar_dados("Insumos") # Colunas: Nome, Qtd, Unidade
    if not df_insumos.empty:
        st.dataframe(df_insumos, use_container_width=True)
    
    with st.expander("Cadastrar Novo Insumo"):
        with st.form("novo_insumo"):
            nome = st.text_input("Nome do Insumo")
            qtd_inicial = st.number_input("Estoque Atual", min_value=0.0)
            unidade = st.selectbox("Unidade", ["kg", "un", "L"])
            
            if st.form_submit_button("Salvar"):
                novo_dado = pd.DataFrame([{"Nome": nome, "Qtd": qtd_inicial, "Unidade": unidade}])
                df_atualizado = pd.concat([df_insumos, novo_dado], ignore_index=True)
                salvar_dados(df_atualizado, "Insumos")
                st.rerun()

# ==========================================
# ABA 3: CAIXA (Financeiro)
# ==========================================
with tab3:
    st.header("Financeiro")
    df_caixa = carregar_dados("Caixa")
    
    if not df_caixa.empty:
        # Garante que as colunas sejam números
        df_caixa['Entrada'] = pd.to_numeric(df_caixa['Entrada'], errors='coerce').fillna(0)
        df_caixa['Saida'] = pd.to_numeric(df_caixa['Saida'], errors='coerce').fillna(0)
        
        entradas = df_caixa['Entrada'].sum()
        saidas = df_caixa['Saida'].sum()
        saldo = entradas - saidas
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", f"R$ {entradas:.2f}")
        c2.metric("Saídas", f"R$ {saidas:.2f}")
        c3.metric("Saldo", f"R$ {saldo:.2f}")
        
        st.divider()
        st.dataframe(df_caixa, use_container_width=True)

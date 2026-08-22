# app.py
import streamlit as st
import pandas as pd
import sqlite3
import os
import re
import json
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="Divisor de Fatura", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("👤 Identificação")
usuario = st.sidebar.text_input("Seu nome (sem espaços):").strip().lower()
if not usuario:
    st.sidebar.error("Insira seu nome para continuar.")
    st.stop()

DB_PATH = f'fatura_{usuario}.db'

# ── Banco de dados ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            norm        TEXT PRIMARY KEY,
            categoria   TEXT,
            dividir_com TEXT
        )
    ''')
    # Migrar dados antigos da tabela transacoes, se existir
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transacoes'")
    if c.fetchone():
        c.execute("SELECT COUNT(*) FROM historico")
        if c.fetchone()[0] == 0:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO historico (norm, categoria, dividir_com)
                    SELECT descricao_norm, categoria, dividir_com
                    FROM transacoes
                    WHERE descricao_norm IS NOT NULL AND categoria IS NOT NULL
                """)
            except Exception:
                pass
    conn.commit()
    return conn

def carregar_historico(conn):
    c = conn.cursor()
    c.execute("SELECT norm, categoria, dividir_com FROM historico")
    return {
        norm: {
            'categoria': cat or '',
            'dividir_com': json.loads(div) if div else []
        }
        for norm, cat, div in c.fetchall()
    }

def salvar_historico(conn, norm, categoria, dividir_com):
    c = conn.cursor()
    c.execute("""
        INSERT INTO historico (norm, categoria, dividir_com) VALUES (?, ?, ?)
        ON CONFLICT(norm) DO UPDATE SET
            categoria   = excluded.categoria,
            dividir_com = excluded.dividir_com
    """, (norm, categoria, json.dumps(dividir_com, ensure_ascii=False)))
    conn.commit()

def limpar_historico(conn):
    conn.cursor().execute("DELETE FROM historico")
    conn.commit()

# ── Parsing e normalização ────────────────────────────────────────────────────
def parse_valor(s):
    """Converte formato brasileiro: '- 1.037,52' → -1037.52"""
    s = str(s).replace(' ', '').replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def extrair_parcela(desc):
    """Captura 'X/Y' de '- Parcela X/Y' no final da descrição."""
    m = re.search(r'-\s*Parcela\s+(\d+)/(\d+)', desc, re.IGNORECASE)
    return f"{m.group(1)}/{m.group(2)}" if m else ''

def normalizar_desc(desc):
    """Remove o sufixo de parcela para agrupar compras parceladas.
    'Amazon - Parcela 3/6' → 'amazon'
    'Uber - NuPay'         → 'uber - nupay'
    """
    d = re.sub(r'\s*-\s*Parcela\s+\d+/\d+\s*$', '', desc, flags=re.IGNORECASE)
    return ' '.join(d.split()).lower()

# ── Exportação Excel ──────────────────────────────────────────────────────────
def gerar_excel(df, caminho, lista_pessoas, usuario):
    wb = Workbook()
    hfill = PatternFill(start_color='DCE6F1', fill_type='solid')

    def estilizar_header(ws, n_cols):
        for col in range(1, n_cols + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.fill = hfill
        for col in range(1, n_cols + 1):
            ws.column_dimensions[get_column_letter(col)].width = 22

    # Aba principal
    ws = wb.active
    ws.title = "Fatura Dividida"
    cols = ['Data', 'Descrição', 'Parcela', 'Categoria', 'Valor (R$)', 'Divide com', 'Valor por pessoa']
    ws.append(cols)
    estilizar_header(ws, len(cols))
    for _, row in df.iterrows():
        ws.append([
            row['Data'].strftime('%d/%m/%Y'),
            row['Descrição'],
            row['Parcela'],
            row['Categoria'],
            row['Valor'],
            ', '.join(row['DivididoCom']),
            row['ValorPorPessoa'],
        ])

    # Aba "O que me devem"
    outros = [p for p in lista_pessoas if p != usuario]
    if outros:
        ws_t = wb.create_sheet("O que me devem")
        ws_t.append(["Pessoa", "Deve (R$)"])
        estilizar_header(ws_t, 2)
        for pessoa in outros:
            total = sum(r['ValorPorPessoa'] for _, r in df.iterrows() if pessoa in r['DivididoCom'])
            ws_t.append([pessoa.title(), round(total, 2)])

    # Aba por pessoa
    for pessoa in lista_pessoas:
        titulo = f"{pessoa[:28]} ({'eu' if pessoa == usuario else 'deve'})"
        ws_p = wb.create_sheet(title=titulo[:31])
        cols_p = ['Data', 'Descrição', 'Parcela', 'Categoria', 'Valor total', 'Divide com', 'Valor pago']
        ws_p.append(cols_p)
        estilizar_header(ws_p, len(cols_p))
        for _, row in df.iterrows():
            if pessoa in row['DivididoCom']:
                ws_p.append([
                    row['Data'].strftime('%d/%m/%Y'),
                    row['Descrição'],
                    row['Parcela'],
                    row['Categoria'],
                    row['Valor'],
                    ', '.join(row['DivididoCom']),
                    row['ValorPorPessoa'],
                ])

    wb.save(caminho)

# ── Interface principal ───────────────────────────────────────────────────────
st.title("🧾 Divisão de Fatura de Cartão")

with st.expander("📋 Como exportar sua fatura Nubank em CSV"):
    st.markdown("""
    1. Abra o app Nubank → **Cartão de Crédito** → **Resumo de Faturas**.
    2. Selecione o mês (só faturas **fechadas** têm opção CSV).
    3. Toque no ícone de envio (canto superior direito) → **CSV**.
    4. O arquivo chega por e-mail no endereço cadastrado na Nubank.
    """)

file = st.file_uploader("📤 Upload da fatura Nubank (.csv)", type="csv")

if file:
    raw = pd.read_csv(file)
    raw.rename(columns={'date': 'Data', 'title': 'Descrição', 'amount': 'Valor'}, inplace=True)
    raw['Data'] = pd.to_datetime(raw['Data'])
    raw['Valor'] = raw['Valor'].apply(parse_valor)
    raw['Parcela'] = raw['Descrição'].apply(extrair_parcela)
    raw['DescNorm'] = raw['Descrição'].apply(normalizar_desc)

    # Separar por tipo
    is_pagamento = raw['Descrição'].str.contains('pagamento recebido', case=False, na=False)
    pagamentos = raw[is_pagamento].copy()
    nao_pagamento = raw[~is_pagamento]
    compras = nao_pagamento[nao_pagamento['Valor'] > 0].copy().reset_index(drop=True)
    estornos = nao_pagamento[nao_pagamento['Valor'] < 0].copy()

    conn = init_db()
    historico = carregar_historico(conn)

    # ── Sidebar: histórico ─────────────────────────────────────────────────
    with st.sidebar.expander("🗃️ Histórico de classificações"):
        st.write(f"Entradas salvas: **{len(historico)}**")
        if historico:
            st.dataframe(pd.DataFrame([
                {'Descrição base': k, 'Categoria': v['categoria']}
                for k, v in historico.items()
            ]), use_container_width=True)
        if st.button("🗑️ Limpar histórico"):
            limpar_historico(conn)
            st.rerun()

    # ── Outras pessoas ─────────────────────────────────────────────────────
    st.subheader("👥 Configuração")
    outros_input = st.text_input(
        "Com quem você divide despesas? (nomes separados por vírgula)",
        placeholder="ex: pedro, maria"
    )
    outros = [p.strip().lower() for p in outros_input.split(',') if p.strip()]
    lista_pessoas = [usuario] + outros  # usuário sempre incluso

    # Estornos/reembolsos (negativos que não são pagamento da fatura)
    if not estornos.empty:
        total_estornos = estornos['Valor'].sum()
        with st.expander(f"↩️ {len(estornos)} estorno(s) / reembolso(s) — total: R$ {total_estornos:.2f}"):
            disp_est = estornos[['Data', 'Descrição', 'Valor']].copy()
            disp_est['Data'] = disp_est['Data'].dt.strftime('%d/%m/%Y')
            disp_est['Valor'] = disp_est['Valor'].apply(lambda x: f'R$ {x:.2f}')
            st.dataframe(disp_est, use_container_width=True)
            st.caption("Esses valores reduzem o total líquido da fatura.")

    # Pagamento da fatura (ignorado)
    if not pagamentos.empty:
        with st.expander(f"ℹ️ {len(pagamentos)} pagamento(s) de fatura ignorado(s)"):
            disp_pag = pagamentos[['Data', 'Descrição', 'Valor']].copy()
            disp_pag['Data'] = disp_pag['Data'].dt.strftime('%d/%m/%Y')
            disp_pag['Valor'] = disp_pag['Valor'].apply(lambda x: f'R$ {x:.2f}')
            st.dataframe(disp_pag, use_container_width=True)

    # ── Métricas ───────────────────────────────────────────────────────────
    n_rec = sum(1 for _, r in compras.iterrows() if r['DescNorm'] in historico)
    m1, m2, m3 = st.columns(3)
    m1.metric("📋 Total de compras", len(compras))
    m2.metric("🔄 Com sugestão do histórico", n_rec)
    m3.metric("🆕 Sem histórico", len(compras) - n_rec)

    # ── Classificação por transação ────────────────────────────────────────
    st.markdown("### 📋 Confirme cada compra")
    st.caption(
        f"Selecione quem divide cada despesa. "
        f"Se deixar só **{usuario}**, é despesa pessoal sua — ninguém deve nada."
    )

    dividido_com_list = []
    valor_por_pessoa_list = []
    categoria_list = []
    salvar_list = []

    for i, row in compras.iterrows():
        norm = row['DescNorm']
        valor = row['Valor']
        parcela = row['Parcela']
        hist = historico.get(norm, {})
        tem_hist = bool(hist)

        prefixo = "✅" if tem_hist else "🆕"
        label = f"{prefixo} {row['Descrição']} | R$ {valor:.2f}"
        if parcela:
            label += f" | Parcela {parcela}"

        with st.expander(label, expanded=not tem_hist):
            if tem_hist:
                st.caption("Sugestão do histórico — confirme ou ajuste.")

            default_cat = hist.get('categoria', '')
            hist_div = hist.get('dividir_com', [usuario])
            default_div = [p for p in hist_div if p in lista_pessoas] or [usuario]

            col1, col2 = st.columns([1, 2])
            with col1:
                cat = st.text_input("Categoria", value=default_cat, key=f"cat_{i}",
                                    placeholder="ex: transporte")
            with col2:
                div = st.multiselect("Quem divide?", options=lista_pessoas,
                                     default=default_div, key=f"div_{i}")

            div_com = div if div else [usuario]
            vpp = round(valor / len(div_com), 2)

            if len(div_com) == 1 and div_com[0] == usuario:
                st.markdown(f"**💳 Despesa pessoal — R$ {valor:.2f} (só você)**")
            else:
                devedores = [p for p in div_com if p != usuario]
                partes = '  |  '.join(f'{p.title()}: R$ {vpp:.2f}' for p in devedores)
                st.markdown(f"**💰 Cada um paga R$ {vpp:.2f}** — Você recebe de: {partes}")

            dividido_com_list.append(div_com)
            valor_por_pessoa_list.append(vpp)
            categoria_list.append(cat)

            if cat:
                salvar_list.append((norm, cat, div_com))

    # Persistir histórico (somente se categoria preenchida)
    for norm, cat, div_com in salvar_list:
        salvar_historico(conn, norm, cat, div_com)

    compras['DivididoCom'] = dividido_com_list
    compras['ValorPorPessoa'] = valor_por_pessoa_list
    compras['Categoria'] = categoria_list

    # ── Resumo ─────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Resumo")

    total_compras = compras['Valor'].sum()
    total_estornos_val = estornos['Valor'].sum() if not estornos.empty else 0.0
    total_liquido = total_compras + total_estornos_val
    minha_parte = sum(
        r['ValorPorPessoa'] for _, r in compras.iterrows() if usuario in r['DivididoCom']
    ) + total_estornos_val  # estornos reduzem a sua parte

    c1, c2, c3 = st.columns(3)
    c1.metric("🛒 Total de compras", f"R$ {total_compras:.2f}")
    c2.metric("↩️ Estornos", f"R$ {total_estornos_val:.2f}")
    c3.metric("💳 Total líquido", f"R$ {total_liquido:.2f}")

    st.metric(f"💼 Minha parte ({usuario.title()})", f"R$ {minha_parte:.2f}")

    if outros:
        st.subheader("💸 O que cada pessoa deve a você")
        cols_dev = st.columns(len(outros))
        for col, pessoa in zip(cols_dev, outros):
            deve = sum(
                r['ValorPorPessoa'] for _, r in compras.iterrows() if pessoa in r['DivididoCom']
            )
            col.metric(f"👤 {pessoa.title()}", f"R$ {deve:.2f}")

    # ── Detalhamento por pessoa ────────────────────────────────────────────
    st.subheader("🧾 Detalhamento por pessoa")
    for pessoa in lista_pessoas:
        label_exp = f"👤 {usuario.title()} (você)" if pessoa == usuario else f"👤 {pessoa.title()}"
        total_p = sum(r['ValorPorPessoa'] for _, r in compras.iterrows() if pessoa in r['DivididoCom'])

        with st.expander(f"{label_exp} — R$ {total_p:.2f}"):
            dados = [
                {
                    'Data': r['Data'].strftime('%d/%m/%Y'),
                    'Descrição': r['Descrição'],
                    'Parcela': r['Parcela'],
                    'Categoria': r['Categoria'],
                    'Valor total': f"R$ {r['Valor']:.2f}",
                    'Divide com': ', '.join(r['DivididoCom']),
                    'Valor pago': f"R$ {r['ValorPorPessoa']:.2f}",
                }
                for _, r in compras.iterrows()
                if pessoa in r['DivididoCom']
            ]
            if dados:
                st.dataframe(pd.DataFrame(dados), use_container_width=True)
            else:
                st.write("Nenhuma despesa.")

    # ── Exportar Excel ─────────────────────────────────────────────────────
    st.subheader("📥 Exportar planilha")
    if st.button("📁 Gerar Excel"):
        nome = f"fatura_{usuario}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        gerar_excel(compras, nome, lista_pessoas, usuario)
        with open(nome, 'rb') as f:
            st.download_button("⬇️ Baixar Excel", f, file_name=nome)
        os.remove(nome)

    conn.close()

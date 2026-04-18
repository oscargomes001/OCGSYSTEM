import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
from datetime import datetime, date, timedelta

st.set_page_config(layout="wide", page_title="OCG System Dashboard")
API_URL = "http://127.0.0.1:8000"

# --- INICIALIZAÇÃO DE SESSÃO ---
if "carrinho" not in st.session_state:
    st.session_state.carrinho = []
if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.cargo = None
    st.session_state.usuario = None

# --- HELPER DE REQUISIÇÕES ---
def safe_request(method, endpoint, params=None, json=None):
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    url = f"{API_URL}/{endpoint}"
    try:
        if method == "GET":
            r = requests.get(url, params=params, headers=headers, timeout=5)
        elif method == "POST":
            r = requests.post(url, json=json, params=params, headers=headers, timeout=5)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=5)
        if r.status_code == 200:
            return r.json()
        else:
            st.error(f"Erro {r.status_code}: {r.text}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Não foi possível conectar ao servidor.")
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
    return None

# ══════════════════════════════════════════════════════════
# FLUXO DE LOGIN
# ══════════════════════════════════════════════════════════
if not st.session_state.token:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.title("🔐 OCG System - Login")
        with st.form("login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", width='stretch'):
                try:
                    resp = requests.post(
                        f"{API_URL}/login",
                        data={"username": u, "password": p},
                        timeout=5
                    )
                    if resp.status_code == 200:
                        d = resp.json()
                        st.session_state.token   = d["access_token"]
                        st.session_state.cargo   = d["cargo"]
                        st.session_state.usuario = u
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Servidor offline. Rode: uvicorn main:app --reload")

# ══════════════════════════════════════════════════════════
# INTERFACE PRINCIPAL
# ══════════════════════════════════════════════════════════
else:
    cargo = st.session_state.cargo
    eh_admin = cargo in ("admin_geral", "admin_restaurante")

    st.sidebar.title(f"Olá, {st.session_state.usuario} 👋")
    st.sidebar.write(f"Nível: **{cargo.upper()}**")

    # Exibe aba de relatórios apenas para admins
    opcoes_menu = ["⚙️ Gerenciamento", "📱 Garçom", "👨‍🍳 Cozinha"]
    if eh_admin:
        opcoes_menu.append("📊 Relatórios")

    menu = st.sidebar.radio("Navegação", opcoes_menu)

    if st.sidebar.button("🚪 Sair", width='stretch'):
        st.session_state.token   = None
        st.session_state.carrinho = []
        st.rerun()

    # ──────────────────────────────────────────────────────
    # 1. GERENCIAMENTO
    # ──────────────────────────────────────────────────────
    if menu == "⚙️ Gerenciamento":
        t_card, t_user = st.tabs(["🍔 Cardápio", "👥 Usuários"])

        with t_card:
            with st.expander("➕ Adicionar Novo Prato", expanded=True):
                n  = st.text_input("Nome do Prato")
                pr = st.number_input("Preço (R$)", min_value=0.0, step=0.5)
                te = st.number_input("Tempo de Preparo (min)", min_value=1, step=1)
                if st.button("💾 Salvar Produto", width='stretch'):
                    if n:
                        payload = {"nome": n, "preco": float(pr), "tempo": int(te)}
                        if safe_request("POST", "produtos/", json=payload):
                            st.success(f"Prato '{n}' cadastrado!")
                            st.rerun()
                    else:
                        st.warning("Digite o nome do prato.")

            st.write("### Itens Atuais")
            prods = safe_request("GET", "produtos/")
            if prods:
                df = pd.DataFrame(prods)
                st.dataframe(df[['nome', 'preco', 'tempo_preparo']], width='stretch')

                st.write("---")
                st.write("#### 🗑️ Remover Produtos")
                cols = st.columns(4)
                for idx, item in enumerate(prods):
                    with cols[idx % 4]:
                        if st.button(f"Remover {item['nome']}", key=f"del_{item['id']}", width='stretch'):
                            safe_request("DELETE", f"produtos/{item['id']}")
                            st.rerun()
            else:
                st.info("Nenhum produto cadastrado ainda.")

        with t_user:
            with st.expander("➕ Novo Usuário/Equipe", expanded=True):
                nu = st.text_input("Login")
                ns = st.text_input("Senha", type="password")
                nc = st.selectbox("Cargo", ["admin_restaurante", "colaborador"])
                if st.button("Criar Acesso", width='stretch'):
                    if nu and ns:
                        if safe_request("POST", "usuarios/salvar", json={"username": nu, "senha": ns, "cargo": nc}):
                            st.success(f"Usuário '{nu}' criado!")
                            st.rerun()
                    else:
                        st.warning("Preencha login e senha.")

            st.write("### Lista de Acessos")
            users = safe_request("GET", "usuarios/listar")
            if users:
                df_u = pd.DataFrame(users)
                st.table(df_u[['username', 'cargo']])

    # ──────────────────────────────────────────────────────
    # 2. GARÇOM
    # ──────────────────────────────────────────────────────
    elif menu == "📱 Garçom":
        st.title("📱 Novo Pedido")
        prods_list = safe_request("GET", "produtos/")

        if prods_list:
            dict_prods = {p['nome']: p for p in prods_list}

            c1, c2, c3 = st.columns([1, 2, 1])
            mesa       = c1.selectbox("Mesa", range(1, 21))
            item_nome  = c2.selectbox("Escolha o Prato", list(dict_prods.keys()))
            quantidade = c3.number_input("Quantidade", min_value=1, value=1)

            if st.button("➕ Adicionar ao Pedido", width='stretch'):
                st.session_state.carrinho.append({
                    "nome": item_nome,
                    "qtd":  int(quantidade),
                    "tempo": dict_prods[item_nome]['tempo_preparo']
                })
                st.rerun()

            if st.session_state.carrinho:
                st.subheader(f"🛒 Itens da Mesa {mesa}")
                st.table(pd.DataFrame(st.session_state.carrinho))

                cb1, cb2 = st.columns(2)
                if cb1.button("🗑️ Limpar Carrinho", width='stretch'):
                    st.session_state.carrinho = []
                    st.rerun()

                if cb2.button("🚀 ENVIAR PEDIDO", type="primary", width='stretch'):
                    payload = {
                        "mesa":   int(mesa),
                        "garcom": st.session_state.usuario,
                        "itens":  st.session_state.carrinho
                    }
                    resultado = safe_request("POST", "pedidos/", json=payload)
                    if resultado:
                        st.session_state.carrinho = []
                        st.success("✅ Pedido enviado para a cozinha!")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("Adicione itens ao pedido.")
        else:
            st.warning("⚠️ Cadastre produtos no Gerenciamento primeiro.")

    # ──────────────────────────────────────────────────────
    # 3. COZINHA
    # ──────────────────────────────────────────────────────
    elif menu == "👨‍🍳 Cozinha":
        import streamlit.components.v1 as components

        hcol1, hcol2 = st.columns([4, 1])
        with hcol1:
            st.title("🍳 Monitor de Pedidos")
            st.caption("OCG SYSTEM · COZINHA AO VIVO")
        with hcol2:
            st.write("")
            st.write("")
            if st.button("⟳ Atualizar", width="stretch"):
                st.rerun()

        pedidos = safe_request("GET", "pedidos/ativos")

        TICKET_CSS = """
            @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;600&display=swap');
            body { margin:0; padding:4px 8px 0 8px; background:transparent; }
            .ticket {
                background:#1a1a1a; border:1px solid #2a2a2a;
                border-left:5px solid #f5a623; border-radius:8px;
                padding:1.2rem 1.5rem; font-family:'DM Sans',sans-serif;
            }
            .ticket-top {
                display:flex; align-items:center; gap:1.2rem;
                margin-bottom:1rem; border-bottom:1px solid #2a2a2a;
                padding-bottom:0.8rem;
            }
            .mesa-badge {
                background:#f5a623; color:#000;
                font-family:'Bebas Neue',sans-serif;
                font-size:2rem; padding:0.1rem 0.8rem;
                border-radius:6px; letter-spacing:2px; line-height:1.2;
            }
            .ticket-meta { flex:1; }
            .ticket-garcom { color:#ccc; font-size:0.95rem; font-weight:600; }
            .ticket-hora   { color:#555; font-size:0.78rem; margin-top:2px; }
            .ticket-id     { color:#333; font-size:0.7rem; font-family:monospace; }
            .itens-titulo  {
                color:#888; font-size:0.7rem; letter-spacing:2px;
                text-transform:uppercase; margin-bottom:0.8rem;
            }
            .item-row {
                display:flex; align-items:center;
                background:#212121; border-radius:8px;
                padding:0.6rem 1rem; margin-bottom:0.5rem; gap:1rem;
            }
            .item-qty {
                background:#f5a623; color:#000;
                font-family:'Bebas Neue',sans-serif;
                font-size:1.3rem; border-radius:6px;
                padding:0 0.5rem; min-width:2rem;
                text-align:center; line-height:1.4;
            }
            .item-nome {
                flex:1; color:#eee;
                font-family:'Bebas Neue',sans-serif;
                font-size:1.2rem; letter-spacing:1px;
            }
            .item-timer {
                font-family:'Bebas Neue',sans-serif;
                font-size:1.5rem; letter-spacing:2px;
                min-width:6rem; text-align:right; transition:color 0.5s;
            }
            .timer-ok      { color:#4caf50; }
            .timer-warning { color:#ff9800; }
            .timer-danger  { color:#f44336; }
            .timer-over    { color:#e53935; animation:pulse 0.8s infinite alternate; }
            @keyframes pulse { from{opacity:1} to{opacity:0.4} }
        """

        if pedidos:
            st.markdown(f"**{len(pedidos)} pedido(s) pendente(s)**")
            st.write("")

            for p in pedidos:
                pid   = p["id"]
                itens = p.get("itens", [])
                hora  = p.get("timestamp", "")

                # Converte timestamp do banco → epoch ms para o timer JS não resetar no rerun
                try:
                    pedido_epoch_ms = int(
                        datetime.strptime(hora, "%Y-%m-%d %H:%M:%S").timestamp() * 1000
                    )
                except Exception:
                    pedido_epoch_ms = "Date.now()"

                itens_html = ""
                timers_js  = ""

                for idx, item in enumerate(itens):
                    timer_id = f"timer_{pid}_{idx}"
                    nome     = item.get("nome", "?")
                    qtd      = item.get("qtd", 1)
                    tempo_m  = int(item.get("tempo", 0))

                    itens_html += f"""
                    <div class="item-row">
                        <div class="item-qty">{qtd}x</div>
                        <div class="item-nome">{nome}</div>
                        <div class="item-timer timer-ok" id="{timer_id}">{tempo_m:02d}:00</div>
                    </div>"""

                    timers_js += f"""
                    (function() {{
                        var el          = document.getElementById('{timer_id}');
                        var total       = {tempo_m} * 60;
                        var pedidoStart = {pedido_epoch_ms};
                        function tick() {{
                            var elapsed   = Math.floor((Date.now() - pedidoStart) / 1000);
                            var remaining = total - elapsed;
                            var neg = remaining < 0;
                            var abs = Math.abs(remaining);
                            var mm  = Math.floor(abs / 60);
                            var ss  = abs % 60;
                            el.textContent = (neg ? '-' : '') + String(mm).padStart(2,'0') + ':' + String(ss).padStart(2,'0');
                            var pct = remaining / (total || 1);
                            el.className = 'item-timer ';
                            if (neg)            el.className += 'timer-over';
                            else if (pct<=0.10) el.className += 'timer-danger';
                            else if (pct<=0.20) el.className += 'timer-warning';
                            else                el.className += 'timer-ok';
                        }}
                        tick();
                        setInterval(tick, 1000);
                    }})();"""

                ticket_html = f"""<!DOCTYPE html><html><head>
                <style>{TICKET_CSS}</style></head><body>
                <div class="ticket">
                    <div class="ticket-top">
                        <div class="mesa-badge">MESA {p["mesa"]}</div>
                        <div class="ticket-meta">
                            <div class="ticket-garcom">&#128100; {p["garcom"]}</div>
                            <div class="ticket-hora">&#128336; Recebido &#224;s {hora}</div>
                            <div class="ticket-id">Pedido #{pid}</div>
                        </div>
                    </div>
                    <div class="itens-titulo">&#9658; ITENS &amp; CONTAGEM REGRESSIVA</div>
                    {itens_html or '<span style="color:#555">Sem itens registrados</span>'}
                </div>
                <script>{timers_js}</script>
                </body></html>"""

                altura = 130 + len(itens) * 60
                components.html(ticket_html, height=altura, scrolling=False)

                if st.button(
                    f"MARCAR MESA {p['mesa']} COMO CONCLUIDA",
                    key=f"r_{pid}",
                    width="stretch"
                ):
                    resultado = safe_request("POST", f"pedidos/{pid}/concluir")
                    if resultado:
                        st.success(f"Mesa {p['mesa']} concluida!")
                        time.sleep(1)
                        st.rerun()
                st.write("")
        else:
            st.markdown("""
            <div style="text-align:center;padding:4rem 0;color:#555;font-size:1.2rem;">
                ✅ <strong>Tudo em dia</strong><br>
                <span style="font-size:0.9rem;color:#444">Nenhum pedido pendente no momento</span>
            </div>
            """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────
    # 4. RELATÓRIOS  (apenas admins)
    # ──────────────────────────────────────────────────────
    elif menu == "📊 Relatórios" and eh_admin:

        st.title("📊 Relatórios")
        st.caption("OCG SYSTEM · PAINEL GERENCIAL")

        # ── Filtro de período ─────────────────────────────
        st.markdown("### 📅 Selecione o Período")

        col_preset, col_vazio = st.columns([2, 3])
        with col_preset:
            preset = st.selectbox(
                "Atalho rápido",
                ["Personalizado", "Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias", "Este mês"],
                index=0
            )

        hoje = date.today()
        if preset == "Hoje":
            d_inicio, d_fim = hoje, hoje
        elif preset == "Ontem":
            d_inicio = d_fim = hoje - timedelta(days=1)
        elif preset == "Últimos 7 dias":
            d_inicio, d_fim = hoje - timedelta(days=6), hoje
        elif preset == "Últimos 30 dias":
            d_inicio, d_fim = hoje - timedelta(days=29), hoje
        elif preset == "Este mês":
            d_inicio = hoje.replace(day=1)
            d_fim    = hoje
        else:
            d_inicio = d_fim = hoje

        col_d1, col_d2, col_btn = st.columns([1, 1, 1])
        with col_d1:
            data_inicio = st.date_input(
                "Data início",
                value=d_inicio,
                max_value=hoje,
                key="rel_inicio"
            )
        with col_d2:
            data_fim = st.date_input(
                "Data fim",
                value=d_fim,
                min_value=data_inicio,
                max_value=hoje,
                key="rel_fim"
            )
        with col_btn:
            st.write("")
            st.write("")
            buscar = st.button("🔍 Gerar Relatório", type="primary", width="stretch")

        st.divider()

        # ── Busca e exibição ──────────────────────────────
        # Gera automaticamente ao entrar na aba ou ao clicar em buscar
        if "rel_dados" not in st.session_state:
            st.session_state.rel_dados     = None
            st.session_state.rel_periodo   = None

        if buscar or st.session_state.rel_dados is None:
            with st.spinner("Carregando dados..."):
                dados = safe_request(
                    "GET", "relatorios/dados",
                    params={
                        "data_inicio": data_inicio.strftime("%Y-%m-%d"),
                        "data_fim":    data_fim.strftime("%Y-%m-%d")
                    }
                )
            if dados is not None:
                st.session_state.rel_dados   = dados
                st.session_state.rel_periodo = (data_inicio, data_fim)
        else:
            dados = st.session_state.rel_dados

        if not dados:
            st.info("Selecione um período e clique em **Gerar Relatório**.")
            st.stop()

        # ── Título do período ─────────────────────────────
        p_ini, p_fim = st.session_state.rel_periodo
        if p_ini == p_fim:
            st.markdown(f"#### Resultados de **{p_ini.strftime('%d/%m/%Y')}**")
        else:
            st.markdown(
                f"#### Resultados de **{p_ini.strftime('%d/%m/%Y')}** "
                f"até **{p_fim.strftime('%d/%m/%Y')}**"
            )

        # ── Cards de métricas ─────────────────────────────
        m1, m2, m3, m4 = st.columns(4)

        fat   = dados.get("faturamento_total", 0)
        n_ped = dados.get("total_pedidos", 0)
        tempo = dados.get("tempo_medio_minutos", 0)
        pratos_lista  = dados.get("pratos", [])
        garcons_lista = dados.get("garcons", [])

        top_prato  = pratos_lista[0]["nome"]  if pratos_lista  else "—"
        top_garcom = garcons_lista[0]["nome"] if garcons_lista else "—"
        ticket_medio = round(fat / n_ped, 2) if n_ped else 0

        m1.metric("💰 Faturamento Total",  f"R$ {fat:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        m2.metric("🍽️ Prato Mais Pedido",  top_prato)
        m3.metric("👨‍🍳 Garçom Destaque",    top_garcom)
        m4.metric("⏱️ Tempo Médio",         f"{tempo} min" if tempo else "—")

        st.write("")

        # ── Gráfico de faturamento (barras + linha) ───────
        fat_dia = dados.get("faturamento_por_dia", [])

        if fat_dia:
            st.markdown("### 📈 Faturamento por Dia")

            df_fat = pd.DataFrame(fat_dia)
            df_fat["data_fmt"] = pd.to_datetime(df_fat["data"]).dt.strftime("%d/%m")

            fig = go.Figure()

            # Barras
            fig.add_trace(go.Bar(
                x=df_fat["data_fmt"],
                y=df_fat["total"],
                name="Faturamento",
                marker_color="#f5a623",
                opacity=0.85,
                hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>"
            ))

            # Linha de tendência
            fig.add_trace(go.Scatter(
                x=df_fat["data_fmt"],
                y=df_fat["total"],
                name="Tendência",
                mode="lines+markers",
                line=dict(color="#ffffff", width=2, dash="dot"),
                marker=dict(size=6, color="#ffffff"),
                hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>"
            ))

            fig.update_layout(
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#cccccc",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=False, tickfont=dict(color="#aaa")),
                yaxis=dict(
                    showgrid=True,
                    gridcolor="#2a2a2a",
                    tickprefix="R$ ",
                    tickfont=dict(color="#aaa")
                ),
                margin=dict(l=10, r=10, t=10, b=10),
                height=340,
                hovermode="x unified"
            )

            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Nenhum dado de faturamento para o período selecionado.")

        st.write("")

        # ── Linha inferior: Pratos | Garçons ─────────────
        col_pratos, col_garcons = st.columns(2)

        with col_pratos:
            st.markdown("### 🍔 Pratos Mais Pedidos")
            if pratos_lista:
                df_pratos = pd.DataFrame(pratos_lista).head(8)

                fig_p = go.Figure(go.Bar(
                    x=df_pratos["quantidade"],
                    y=df_pratos["nome"],
                    orientation="h",
                    marker_color="#f5a623",
                    hovertemplate="<b>%{y}</b><br>%{x} unidades<extra></extra>"
                ))
                fig_p.update_layout(
                    plot_bgcolor="#1a1a1a",
                    paper_bgcolor="#1a1a1a",
                    font_color="#cccccc",
                    xaxis=dict(showgrid=True, gridcolor="#2a2a2a", tickfont=dict(color="#aaa")),
                    yaxis=dict(showgrid=False, tickfont=dict(color="#eee"), autorange="reversed"),
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=300
                )
                st.plotly_chart(fig_p, width="stretch")

                # Tabela detalhada
                df_show = df_pratos[["nome", "quantidade", "faturamento"]].copy()
                df_show.columns = ["Prato", "Qtd", "Faturamento (R$)"]
                df_show["Faturamento (R$)"] = df_show["Faturamento (R$)"].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                st.dataframe(df_show, hide_index=True, width="stretch")
            else:
                st.info("Nenhum prato no período.")

        with col_garcons:
            st.markdown("### 🧑‍💼 Desempenho dos Garçons")
            if garcons_lista:
                df_garc = pd.DataFrame(garcons_lista)

                # Gráfico de pizza
                fig_g = go.Figure(go.Pie(
                    labels=df_garc["nome"],
                    values=df_garc["pedidos"],
                    hole=0.45,
                    marker=dict(colors=["#f5a623", "#e8890c", "#c97000", "#a85c00", "#7a4200"]),
                    hovertemplate="<b>%{label}</b><br>%{value} pedidos (%{percent})<extra></extra>",
                    textfont=dict(color="#ffffff")
                ))
                fig_g.update_layout(
                    plot_bgcolor="#1a1a1a",
                    paper_bgcolor="#1a1a1a",
                    font_color="#cccccc",
                    legend=dict(font=dict(color="#ccc")),
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=300
                )
                st.plotly_chart(fig_g, width="stretch")

                # Tabela detalhada
                df_show_g = df_garc[["nome", "pedidos", "faturamento"]].copy()
                df_show_g.columns = ["Garçom", "Pedidos", "Faturamento (R$)"]
                df_show_g["Faturamento (R$)"] = df_show_g["Faturamento (R$)"].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                st.dataframe(df_show_g, hide_index=True, width="stretch")
            else:
                st.info("Nenhum garçom no período.")

        st.write("")

        # ── Rodapé com resumo textual ─────────────────────
        st.divider()
        resumo_cols = st.columns(3)
        resumo_cols[0].metric("🧾 Total de Pedidos",  n_ped)
        resumo_cols[1].metric("🎫 Ticket Médio",
            f"R$ {ticket_medio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        resumo_cols[2].metric("📦 Itens Distintos",   len(pratos_lista))
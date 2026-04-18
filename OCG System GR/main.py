from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List
import json as _json
import os
import database as db

# --- 1. CONFIGURAÇÃO INICIAL ---
app = FastAPI(title="OCG System API")
ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════
# AUTO-SETUP: carrega master_credentials.json e garante
# que o usuário master existe no banco ao iniciar o servidor
# ══════════════════════════════════════════════════════════
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "master_credentials.json")

def garantir_usuario_master():
    if not os.path.exists(CREDENTIALS_FILE):
        print("⚠️  master_credentials.json não encontrado. Pulando setup automático.")
        return

    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        creds = _json.load(f)

    repo = db.SessionLocal()
    try:
        user = repo.query(db.Usuario).filter(
            db.Usuario.username == creds["username"]
        ).first()

        if user:
            # Atualiza a senha e cargo caso o arquivo tenha mudado
            user.senha_hash = ph.hash(creds["senha"])
            user.cargo      = creds["cargo"]
            repo.commit()
            print(f"✅ Usuário master '{creds['username']}' atualizado.")
        else:
            repo.add(db.Usuario(
                username   = creds["username"],
                senha_hash = ph.hash(creds["senha"]),
                cargo      = creds["cargo"]
            ))
            repo.commit()
            print(f"✅ Usuário master '{creds['username']}' criado automaticamente.")
    finally:
        repo.close()

# Executa ao iniciar o servidor
garantir_usuario_master()

# --- 2. SCHEMAS (Pydantic) ---
class ProdutoSchema(BaseModel):
    nome: str
    preco: float
    tempo: int

class UserSchema(BaseModel):
    username: str
    senha: str
    cargo: str

class ItemPedidoSchema(BaseModel):
    nome: str
    qtd: int
    tempo: int

class PedidoSchema(BaseModel):
    mesa: int
    garcom: str
    itens: List[ItemPedidoSchema]

# --- 3. DEPENDÊNCIA DO BANCO ---
def get_db():
    repo = db.SessionLocal()
    try:
        yield repo
    finally:
        repo.close()

# --- 4. LOGIN ---
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), repo: Session = Depends(get_db)):
    user = repo.query(db.Usuario).filter(db.Usuario.username == form_data.username).first()
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    try:
        ph.verify(user.senha_hash, form_data.password)
        return {
            "access_token": user.username,
            "token_type":   "bearer",
            "cargo":        user.cargo
        }
    except VerifyMismatchError:
        raise HTTPException(status_code=400, detail="Senha incorreta")

# --- 5. USUÁRIOS ---
@app.post("/usuarios/salvar")
def salvar_usuario(dados: UserSchema, repo: Session = Depends(get_db)):
    user   = repo.query(db.Usuario).filter(db.Usuario.username == dados.username.strip()).first()
    hash_s = ph.hash(dados.senha)
    if user:
        user.senha_hash = hash_s
        user.cargo      = dados.cargo
    else:
        repo.add(db.Usuario(
            username   = dados.username.strip(),
            senha_hash = hash_s,
            cargo      = dados.cargo
        ))
    repo.commit()
    return {"status": "Usuário salvo"}

@app.get("/usuarios/listar")
def listar_usuarios(repo: Session = Depends(get_db)):
    users = repo.query(db.Usuario).all()
    return [{"username": u.username, "cargo": u.cargo} for u in users]

# --- 6. PRODUTOS ---
@app.post("/produtos/")
def salvar_produto(dados: ProdutoSchema, repo: Session = Depends(get_db)):
    nome_f = dados.nome.strip().title()
    prod   = repo.query(db.Produto).filter(db.Produto.nome == nome_f).first()
    if prod:
        prod.preco        = dados.preco
        prod.tempo_preparo = dados.tempo
    else:
        repo.add(db.Produto(nome=nome_f, preco=dados.preco, tempo_preparo=dados.tempo))
    repo.commit()
    return {"status": "Produto salvo"}

@app.get("/produtos/")
def listar_produtos(repo: Session = Depends(get_db)):
    prods = repo.query(db.Produto).all()
    return [
        {"id": p.id, "nome": p.nome, "preco": p.preco, "tempo_preparo": p.tempo_preparo}
        for p in prods
    ]

@app.delete("/produtos/{id}")
def deletar_produto(id: int, repo: Session = Depends(get_db)):
    prod = repo.query(db.Produto).filter(db.Produto.id == id).first()
    if prod:
        repo.delete(prod)
        repo.commit()
    return {"status": "Removido"}

# --- 7. PEDIDOS ---
@app.post("/pedidos/")
def emitir_pedido(dados: PedidoSchema, repo: Session = Depends(get_db)):
    itens_estruturados = [
        {"nome": i.nome, "qtd": i.qtd, "tempo": i.tempo}
        for i in dados.itens
    ]
    novo_pedido = db.Pedido(
        mesa      = str(dados.mesa),
        garcom    = dados.garcom,
        status    = "Pendente",
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        itens_json= _json.dumps(itens_estruturados, ensure_ascii=False)
    )
    repo.add(novo_pedido)
    repo.flush()

    for item in dados.itens:
        repo.add(db.ItemPedido(
            pedido_id    = novo_pedido.id,
            produto_nome = item.nome,
            quantidade   = item.qtd,
            tempo_preparo= item.tempo
        ))

    repo.commit()
    return {"status": "Pedido enviado com sucesso", "pedido_id": novo_pedido.id}

@app.get("/pedidos/ativos")
def pedidos_ativos(repo: Session = Depends(get_db)):
    pedidos = repo.query(db.Pedido).filter(db.Pedido.status == "Pendente").all()
    resultado = []
    for p in pedidos:
        try:
            itens = _json.loads(p.itens_json)
            if not isinstance(itens, list):
                raise ValueError
        except Exception:
            itens = [
                {"nome": parte.strip(), "qtd": 1, "tempo": 0}
                for parte in (p.itens_json or "").split(",")
                if parte.strip()
            ]
        resultado.append({
            "id":        p.id,
            "mesa":      p.mesa,
            "garcom":    p.garcom,
            "status":    p.status,
            "timestamp": p.timestamp,
            "itens":     itens
        })
    return resultado

@app.post("/pedidos/{id}/concluir")
def concluir_pedido(id: int, repo: Session = Depends(get_db)):
    pedido = repo.query(db.Pedido).filter(db.Pedido.id == id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    pedido.status       = "Concluído"
    pedido.finalizado_em = datetime.now()
    repo.commit()
    return {"status": "Pedido concluído"}

# --- 8. RELATÓRIOS ---
@app.get("/relatorios/dados")
def relatorio_dados(
    data_inicio: str  = Query(..., description="Data início YYYY-MM-DD"),
    data_fim:    str  = Query(..., description="Data fim   YYYY-MM-DD"),
    repo:        Session = Depends(get_db)
):
    try:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim    = datetime.strptime(data_fim,    "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato inválido. Use YYYY-MM-DD.")

    str_inicio = dt_inicio.strftime("%Y-%m-%d")
    str_fim    = dt_fim.strftime("%Y-%m-%d")

    pedidos = repo.query(db.Pedido).filter(
        db.Pedido.status    == "Concluído",
        db.Pedido.timestamp >= str_inicio,
        db.Pedido.timestamp <  str_fim
    ).all()

    if not pedidos:
        return {
            "faturamento_total":   0,
            "total_pedidos":       0,
            "faturamento_por_dia": [],
            "pratos":              [],
            "garcons":             [],
            "tempo_medio_minutos": 0
        }

    preco_map = {
        p.nome.strip().lower(): p.preco
        for p in repo.query(db.Produto).all()
    }

    faturamento_total = 0.0
    fat_por_dia       = {}
    contagem_pratos   = {}
    contagem_garcons  = {}
    tempos            = []

    for pedido in pedidos:
        try:
            itens = _json.loads(pedido.itens_json)
            if not isinstance(itens, list):
                raise ValueError
        except Exception:
            itens = []

        fat_pedido = 0.0
        for item in itens:
            nome_item = item.get("nome", "").strip()
            qtd       = int(item.get("qtd", 1))
            preco     = preco_map.get(nome_item.lower(), 0.0)
            fat_item  = preco * qtd
            fat_pedido += fat_item

            chave = nome_item.title()
            if chave not in contagem_pratos:
                contagem_pratos[chave] = {"qtd": 0, "fat": 0.0}
            contagem_pratos[chave]["qtd"] += qtd
            contagem_pratos[chave]["fat"] += fat_item

        faturamento_total += fat_pedido

        dia = pedido.timestamp[:10]
        fat_por_dia[dia] = fat_por_dia.get(dia, 0.0) + fat_pedido

        garcom = pedido.garcom or "Desconhecido"
        if garcom not in contagem_garcons:
            contagem_garcons[garcom] = {"pedidos": 0, "fat": 0.0}
        contagem_garcons[garcom]["pedidos"] += 1
        contagem_garcons[garcom]["fat"]     += fat_pedido

        if pedido.finalizado_em and pedido.timestamp:
            try:
                t0    = datetime.strptime(pedido.timestamp, "%Y-%m-%d %H:%M:%S")
                delta = (pedido.finalizado_em - t0).total_seconds() / 60
                if 0 < delta < 300:
                    tempos.append(delta)
            except Exception:
                pass

    fat_dia_lista = sorted(
        [{"data": k, "total": round(v, 2)} for k, v in fat_por_dia.items()],
        key=lambda x: x["data"]
    )
    pratos_lista = sorted(
        [{"nome": k, "quantidade": v["qtd"], "faturamento": round(v["fat"], 2)}
         for k, v in contagem_pratos.items()],
        key=lambda x: x["quantidade"], reverse=True
    )
    garcons_lista = sorted(
        [{"nome": k, "pedidos": v["pedidos"], "faturamento": round(v["fat"], 2)}
         for k, v in contagem_garcons.items()],
        key=lambda x: x["pedidos"], reverse=True
    )

    return {
        "faturamento_total":   round(faturamento_total, 2),
        "total_pedidos":       len(pedidos),
        "faturamento_por_dia": fat_dia_lista,
        "pratos":              pratos_lista,
        "garcons":             garcons_lista,
        "tempo_medio_minutos": round(sum(tempos) / len(tempos), 1) if tempos else 0
    }
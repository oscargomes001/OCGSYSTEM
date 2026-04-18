from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()
engine = create_engine('sqlite:///restaurante.db', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    cargo = Column(String, nullable=False)

class Produto(Base):
    __tablename__ = 'produtos'
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)
    preco = Column(Float)
    tempo_preparo = Column(Integer)

class Funcionario(Base):
    __tablename__ = 'funcionarios'
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)

class Pedido(Base):
    __tablename__ = 'pedidos'
    id = Column(Integer, primary_key=True)
    mesa = Column(String)
    garcom = Column(String)
    status = Column(String, default="Pendente")
    timestamp = Column(String)
    finalizado_em = Column(DateTime, nullable=True)
    itens_json = Column(String)  # <- coluna que estava faltando

    itens = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")

class ItemPedido(Base):
    __tablename__ = 'itens_pedido'
    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.id'))
    produto_nome = Column(String)
    quantidade = Column(Integer)
    tempo_preparo = Column(Integer)
    pedido = relationship("Pedido", back_populates="itens")

# Cria/atualiza as tabelas no SQLite
Base.metadata.create_all(bind=engine)
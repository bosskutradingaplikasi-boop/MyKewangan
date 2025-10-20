
import os
from datetime import datetime, timedelta
import pytz
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TIMEZONE = os.getenv("TIMEZONE", "UTC")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define table models
class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    jenis = Column(String, index=True)  # 'masuk' or 'keluar'
    amaun = Column(Float)
    kategori = Column(String, nullable=True)
    nota = Column(String, nullable=True)
    tarikh = Column(DateTime, default=lambda: datetime.now(pytz.timezone(TIMEZONE)))

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    nama = Column(String)
    status = Column(String(10), default='free') # free or premium
    subscription_start = Column(DateTime, nullable=True)
    subscription_end = Column(DateTime, nullable=True)
    auto_laporan = Column(String(3), default='off') # on or off

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- User Management ---
def get_or_create_user(db, telegram_id, nama):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, nama=nama)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# --- Transaction Management ---
def add_transaction(db, user_id: int, jenis: str, amaun: float, kategori: str, nota: str):
    tz = pytz.timezone(TIMEZONE)
    new_trans = Transaction(
        user_id=user_id,
        jenis=jenis,
        amaun=amaun,
        kategori=kategori,
        nota=nota,
        tarikh=datetime.now(tz)
    )
    db.add(new_trans)
    db.commit()
    db.refresh(new_trans)
    return new_trans

def get_transactions(db, user_id: int, period: str):
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()
    
    if period == 'harian':
        start_date = today
    elif period == 'mingguan':
        start_date = today - timedelta(days=today.weekday())
    elif period == 'bulanan':
        start_date = today.replace(day=1)
    else:
        return []

    start_datetime = tz.localize(datetime.combine(start_date, datetime.min.time()))
    
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.tarikh >= start_datetime
    ).order_by(Transaction.tarikh.desc()).all()

def get_balance(db, user_id: int):
    total_masuk = db.query(func.sum(Transaction.amaun)).filter(
        Transaction.user_id == user_id,
        Transaction.jenis == 'masuk'
    ).scalar() or 0.0

    total_keluar = db.query(func.sum(Transaction.amaun)).filter(
        Transaction.user_id == user_id,
        Transaction.jenis == 'keluar'
    ).scalar() or 0.0

    return total_masuk - total_keluar

def delete_transaction(db, user_id: int, transaction_id: int):
    trans_to_delete = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id
    ).first()

    if trans_to_delete:
        db.delete(trans_to_delete)
        db.commit()
        return trans_to_delete
    return None

def get_kategori(db, user_id: int):
    return db.query(Transaction.kategori).filter(
        Transaction.user_id == user_id, 
        Transaction.kategori.isnot(None)
    ).distinct().all()

def get_all_transactions_by_user(db, user_id: int):
    """Gets all transactions for a specific user, ordered by date."""
    return db.query(Transaction).filter(Transaction.user_id == user_id).order_by(Transaction.tarikh.desc()).all()

def count_transactions(db, user_id: int) -> int:
    """Counts the total number of transactions for a specific user."""
    return db.query(Transaction).filter(Transaction.user_id == user_id).count()

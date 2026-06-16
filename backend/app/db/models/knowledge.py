import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class KnowledgeEntry(Base):
    """
    Persistent knowledge base the AI consults before every trade.
    Seeded with proven trading frameworks; grows with each episode review.
    """
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[str] = mapped_column(String, index=True)  # risk | regime | strategy | lesson
    market: Mapped[str] = mapped_column(String, default="all") # all | crypto | us_stocks | india | forex
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="system")   # system | episode_review
    importance: Mapped[int] = mapped_column(Integer, default=5)
    times_referenced: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

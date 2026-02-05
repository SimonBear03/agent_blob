"""
Data models for memory system.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum
import json


class MemoryType(str, Enum):
    """Types of memories that can be extracted"""
    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    QUESTION = "question"
    PROJECT = "project"


@dataclass
class Memory:
    """A single extracted memory"""
    id: str
    timestamp: str
    session_id: str
    type: MemoryType
    content: str
    context: str
    importance: int  # 1-10
    tags: List[str] = field(default_factory=list)
    source_messages: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    supersedes: Optional[str] = None  # ID of memory this replaces
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['type'] = self.type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """Create from dictionary"""
        data = data.copy()
        data['type'] = MemoryType(data['type'])
        return cls(**data)
    
    def to_json_line(self) -> str:
        """Convert to JSONL format"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json_line(cls, line: str) -> "Memory":
        """Parse from JSONL format"""
        data = json.loads(line)
        return cls.from_dict(data)
    
    def to_search_text(self) -> str:
        """Get text representation for search indexing"""
        parts = [
            self.content,
            self.context,
            " ".join(self.tags)
        ]
        return " ".join(parts)


@dataclass
class MemoryExtractionResult:
    """Result from memory extraction"""
    memories: List[Memory]
    extraction_time: float
    tokens_used: int

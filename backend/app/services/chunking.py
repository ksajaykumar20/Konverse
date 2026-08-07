"""Document chunking — LangChain's RecursiveCharacterTextSplitter.

Kept narrowly scoped: we use only the splitter, not LangChain chains/agents.
Defaults chosen for OpenAI text-embedding-3-small (8k token limit) with
~20% overlap so boundary context isn't lost across chunks.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Approved in Phase 3: 1000 chars per chunk, 200 overlap.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=DEFAULT_CHUNK_SIZE,
    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    separators=["\n\n", "\n", ".", " ", ""],
    length_function=len,
)


def split_text(text: str) -> list[str]:
    """Split extracted text into non-empty chunks for embedding."""
    return [c for c in _splitter.split_text(text) if c and c.strip()]
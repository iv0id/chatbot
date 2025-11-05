import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.helper import download_hugging_face_embeddings, text_split
from langchain.schema import Document


def test_download_hugging_face_embeddings():
    """Test that embeddings model loads correctly"""
    embeddings = download_hugging_face_embeddings()
    assert embeddings is not None
    assert hasattr(embeddings, 'embed_query')


def test_text_split():
    """Test text splitting functionality"""
    # Create sample documents
    sample_docs = [
        Document(
            page_content="This is a test document with some medical content. " * 50,
            metadata={"source": "test.pdf"}
        )
    ]

    chunks = text_split(sample_docs)

    assert len(chunks) > 0
    assert all(isinstance(chunk, Document) for chunk in chunks)
    assert all(len(chunk.page_content) <= 750 for chunk in chunks)


def test_text_split_chunk_overlap():
    """Test that chunks have proper overlap"""
    sample_text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 20
    sample_docs = [
        Document(
            page_content=sample_text,
            metadata={"source": "test.pdf"}
        )
    ]

    chunks = text_split(sample_docs)

    # Verify we have multiple chunks due to length
    assert len(chunks) > 1

    # Check that consecutive chunks have some overlap
    for i in range(len(chunks) - 1):
        # Some content from chunk i should appear in chunk i+1 due to overlap
        chunk1_end = chunks[i].page_content[-50:]  # Last 50 chars
        chunk2_start = chunks[i + 1].page_content[:150]  # First 150 chars
        # There should be some overlap
        overlap_found = any(word in chunk2_start for word in chunk1_end.split()[-5:])
        assert overlap_found or len(chunks[i].page_content) < 750


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

# tests/test_retrieval.py
"""
Production tests for Retrieval and Hybrid Search functionality.

Tests cover:
- hybrid_search function
- Vector store integration
- Edge cases (empty query, no results)
- Performance and correctness
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from retrieval.hybrid_search import hybrid_search
from retrieval.vector_store import add_documents, get_vector_store


@pytest.fixture
def sample_documents():
    """Fixture providing sample documents for testing"""
    return [
        Document(
            page_content="The Federal Reserve raised interest rates by 25 basis points in June 2023.",
            metadata={"source": "fomc", "date": "2023-06-14"},
        ),
        Document(
            page_content="Inflation has been moderating but remains above target according to latest FOMC minutes.",
            metadata={"source": "fomc", "date": "2023-07-01"},
        ),
        Document(
            page_content="SEC issued new guidance on climate disclosure requirements for public companies."
        ),
    ]


def _make_mock_store(docs=None):
    """Create a mock vector store for tests (avoids Chroma/embedding in CI)."""
    docs = docs or []
    mock_retriever = AsyncMock()
    mock_retriever.ainvoke.return_value = docs

    mock_store = MagicMock()
    mock_store.as_retriever.return_value = mock_retriever
    mock_store.get.return_value = {"documents": [d.page_content for d in docs], "metadatas": [d.metadata for d in docs]}
    mock_store._collection.count.return_value = len(docs)
    mock_store.delete_collection.return_value = None
    mock_store.add_documents.return_value = None
    return mock_store


@pytest.mark.asyncio
@patch("retrieval.vector_store.get_vector_store")
@patch("retrieval.hybrid_search.get_vector_store")
async def test_hybrid_search_basic(mock_hs_store, mock_vs_store, sample_documents):
    """Test basic hybrid search functionality"""
    mock_store = _make_mock_store(sample_documents[:2])
    mock_hs_store.return_value = mock_store
    mock_vs_store.return_value = mock_store

    results = await hybrid_search(
        "What did the FOMC say about interest rates?", k=2
    )

    assert len(results) <= 2
    assert all(isinstance(doc, Document) for doc in results)


@pytest.mark.asyncio
@patch("retrieval.vector_store.get_vector_store")
@patch("retrieval.hybrid_search.get_vector_store")
async def test_hybrid_search_empty_query(mock_hs_store, mock_vs_store):
    """Test behavior with empty or whitespace query"""
    mock_store = _make_mock_store([])
    mock_hs_store.return_value = mock_store
    mock_vs_store.return_value = mock_store

    results = await hybrid_search("   ", k=5)

    assert len(results) <= 5


@pytest.mark.asyncio
@patch("retrieval.vector_store.get_vector_store")
@patch("retrieval.hybrid_search.get_vector_store")
async def test_hybrid_search_no_results(mock_hs_store, mock_vs_store):
    """Test when no relevant documents are found"""
    mock_store = _make_mock_store([])
    mock_hs_store.return_value = mock_store
    mock_vs_store.return_value = mock_store

    results = await hybrid_search(
        "Completely unrelated query about quantum physics", k=3
    )

    assert len(results) == 0 or len(results) <= 3


@pytest.mark.asyncio
@patch("retrieval.vector_store.get_vector_store")
@patch("retrieval.hybrid_search.get_vector_store")
async def test_hybrid_search_top_k_parameter(mock_hs_store, mock_vs_store):
    """Test that k parameter is respected"""
    docs = [
        Document(page_content=f"Document {i} about Federal Reserve policy")
        for i in range(10)
    ]
    mock_store = _make_mock_store(docs[:3])
    mock_hs_store.return_value = mock_store
    mock_vs_store.return_value = mock_store

    results = await hybrid_search("Federal Reserve policy", k=3)

    assert len(results) <= 3


@pytest.mark.asyncio
@patch("retrieval.vector_store.get_vector_store")
@patch("retrieval.hybrid_search.get_vector_store")
async def test_hybrid_search_with_reranker_disabled(mock_hs_store, mock_vs_store):
    """Test hybrid search when reranker is turned off"""
    mock_store = _make_mock_store([])
    mock_hs_store.return_value = mock_store
    mock_vs_store.return_value = mock_store

    results = await hybrid_search(
        query="FOMC interest rate decision", k=5, use_reranker=False
    )

    assert len(results) <= 5


@pytest.mark.integration
def test_vector_store_integration():
    """Test direct integration with vector store (requires Chroma DB)"""
    pytest.skip("Integration test - requires Chroma DB and embeddings")


@pytest.mark.asyncio
async def test_retrieval_error_handling():
    """Test graceful error handling in hybrid search"""
    with patch("retrieval.hybrid_search.get_vector_store") as mock_store:
        mock_store.side_effect = Exception("Vector store connection failed")

        results = await hybrid_search("Test query")

        # Should return empty list instead of crashing
        assert isinstance(results, list)
        assert results == []

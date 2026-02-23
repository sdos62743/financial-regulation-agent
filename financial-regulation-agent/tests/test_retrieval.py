# tests/test_retrieval.py
"""
Production tests for Retrieval and Hybrid Search functionality.

Tests cover:
- hybrid_search function
- Vector store integration
- Edge cases (empty query, no results)
- Performance and correctness
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

from retrieval.hybrid_search import hybrid_search
from retrieval.vector_store import get_vector_store, add_documents
from langchain_core.documents import Document


@pytest.fixture
def sample_documents():
    """Fixture providing sample documents for testing"""
    return [
        Document(page_content="The Federal Reserve raised interest rates by 25 basis points in June 2023.", 
                 metadata={"source": "fomc", "date": "2023-06-14"}),
        Document(page_content="Inflation has been moderating but remains above target according to latest FOMC minutes.", 
                 metadata={"source": "fomc", "date": "2023-07-01"}),
        Document(page_content="SEC issued new guidance on climate disclosure requirements for public companies."),
    ]


@pytest.mark.asyncio
async def test_hybrid_search_basic(sample_documents):
    """Test basic hybrid search functionality"""
    # Add sample documents to vector store
    add_documents(sample_documents)

    results = await hybrid_search("What did the FOMC say about interest rates?", top_k=2)

    assert len(results) == 2
    assert all(isinstance(doc, Document) for doc in results)
    assert any("interest rates" in doc.page_content.lower() for doc in results)


@pytest.mark.asyncio
async def test_hybrid_search_empty_query():
    """Test behavior with empty or whitespace query"""
    results = await hybrid_search("   ", top_k=5)
    
    assert len(results) <= 5  # Should not crash, may return empty or default results


@pytest.mark.asyncio
async def test_hybrid_search_no_results():
    """Test when no relevant documents are found"""
    # Clear store for this test
    store = get_vector_store()
    store.delete_collection()

    results = await hybrid_search("Completely unrelated query about quantum physics", top_k=3)
    
    assert len(results) == 0 or len(results) <= 3  # Should handle gracefully


@pytest.mark.asyncio
async def test_hybrid_search_top_k_parameter():
    """Test that top_k parameter is respected"""
    add_documents([
        Document(page_content=f"Document {i} about Federal Reserve policy") 
        for i in range(10)
    ])

    results = await hybrid_search("Federal Reserve policy", top_k=3)
    
    assert len(results) == 3


@pytest.mark.asyncio
async def test_hybrid_search_with_reranker_disabled():
    """Test hybrid search when reranker is turned off"""
    results = await hybrid_search(
        query="FOMC interest rate decision",
        top_k=5,
        use_reranker=False
    )
    
    assert len(results) <= 5


def test_vector_store_integration():
    """Test direct integration with vector store"""
    store = get_vector_store()
    
    # Add test document
    test_doc = Document(page_content="Test document for retrieval evaluation", 
                       metadata={"test": True})
    add_documents([test_doc])
    
    # Check count
    count = store._collection.count()
    assert count > 0


@pytest.mark.asyncio
async def test_retrieval_error_handling():
    """Test graceful error handling in hybrid search"""
    with patch('retrieval.hybrid_search.get_vector_store') as mock_store:
        mock_store.side_effect = Exception("Vector store connection failed")
        
        results = await hybrid_search("Test query")
        
        # Should return empty list instead of crashing
        assert isinstance(results, list)
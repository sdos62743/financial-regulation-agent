#!/usr/bin/env python3
"""
Print vector store document counts: total and by category (regulator, source_type, type, spider).
Run from project root: python scripts/count_db.py (Makefile does this).
"""

import sys
from collections import Counter
from pathlib import Path

# Add project root to path for imports (retrieval.vector_store loads .env)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval.vector_store import get_vector_store

vs = get_vector_store()
coll = vs._collection

# Total count
total = coll.count()
print(f"📊 Total documents in vector store: {total}")

if total == 0:
    print("   (No documents to show category breakdown)")
    exit(0)

# Get all metadata for category-wise counts
result = coll.get(include=["metadatas"])
metadatas = result.get("metadatas") or []

# Count by category
by_regulator = Counter()
by_source_type = Counter()
by_type = Counter()
by_spider = Counter()

for m in metadatas:
    if m:
        by_regulator[m.get("regulator") or "(none)"] += 1
        by_source_type[m.get("source_type") or "(none)"] += 1
        by_type[m.get("type") or "(none)"] += 1
        by_spider[m.get("spider") or "(none)"] += 1

print("\n   By regulator:")
for k, v in sorted(by_regulator.items(), key=lambda x: -x[1]):
    print(f"      {k}: {v}")

print("\n   By source_type:")
for k, v in sorted(by_source_type.items(), key=lambda x: -x[1]):
    print(f"      {k}: {v}")

print("\n   By type:")
for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
    print(f"      {k}: {v}")

print("\n   By spider:")
for k, v in sorted(by_spider.items(), key=lambda x: -x[1]):
    print(f"      {k}: {v}")

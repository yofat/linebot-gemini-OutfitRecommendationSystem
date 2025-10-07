"""Test Rakuten API search with generated queries.

Usage:
  python scripts/test_rakuten_search.py
  
Environment variables required:
  RAKUTEN_APP_ID - Your Rakuten application ID
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from shopping_queries import build_queries
from shopping_rakuten import search_items


def test_queries():
    """Test different query patterns."""
    
    # Check if API key is set
    if not os.getenv('RAKUTEN_APP_ID'):
        print("❌ Error: RAKUTEN_APP_ID environment variable not set")
        print("Please set it first: $env:RAKUTEN_APP_ID='your_app_id'")
        return
    
    print("🔍 Testing Rakuten API Search\n")
    print("=" * 60)
    
    # Test case 1: Multiple items with colors
    print("\n📋 Test Case 1: Multiple items with colors")
    print("-" * 60)
    suggestions1 = ['カーディガン', 'ベージュ ワンピース', 'ブラウン スニーカー']
    print(f"Suggestions: {suggestions1}")
    
    queries1 = build_queries(suggestions1, '', '', gender='レディース')
    print(f"\nGenerated {len(queries1)} queries:")
    for i, q in enumerate(queries1, 1):
        print(f"  {i}. {q}")
    
    print("\nSearching Rakuten API...")
    for i, query in enumerate(queries1, 1):
        print(f"\n🔎 Query {i}: '{query}'")
        try:
            results = search_items(query, max_results=3, qps=1.0)
            print(f"   ✅ Found {len(results)} products")
            if results:
                for j, product in enumerate(results[:2], 1):
                    print(f"      {j}. {product.get('title', 'N/A')[:50]}...")
                    print(f"         ¥{product.get('price', 'N/A'):,} - {product.get('shop', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test case 2: Male clothing
    print("\n\n📋 Test Case 2: Male clothing")
    print("-" * 60)
    suggestions2 = ['ホワイト シャツ', 'ネイビー パンツ']
    print(f"Suggestions: {suggestions2}")
    
    queries2 = build_queries(suggestions2, '', '', gender='メンズ')
    print(f"\nGenerated {len(queries2)} queries:")
    for i, q in enumerate(queries2, 1):
        print(f"  {i}. {q}")
    
    print("\nSearching Rakuten API...")
    for i, query in enumerate(queries2, 1):
        print(f"\n🔎 Query {i}: '{query}'")
        try:
            results = search_items(query, max_results=3, qps=1.0)
            print(f"   ✅ Found {len(results)} products")
            if results:
                for j, product in enumerate(results[:2], 1):
                    print(f"      {j}. {product.get('title', 'N/A')[:50]}...")
                    print(f"         ¥{product.get('price', 'N/A'):,} - {product.get('shop', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test case 3: Simple items without colors
    print("\n\n📋 Test Case 3: Simple items without colors")
    print("-" * 60)
    suggestions3 = ['カーディガン', 'ワンピース']
    print(f"Suggestions: {suggestions3}")
    
    queries3 = build_queries(suggestions3, '', '', gender='レディース')
    print(f"\nGenerated {len(queries3)} queries:")
    for i, q in enumerate(queries3, 1):
        print(f"  {i}. {q}")
    
    print("\nSearching Rakuten API...")
    total_found = 0
    for i, query in enumerate(queries3, 1):
        print(f"\n🔎 Query {i}: '{query}'")
        try:
            results = search_items(query, max_results=3, qps=1.0)
            print(f"   ✅ Found {len(results)} products")
            total_found += len(results)
            if results:
                for j, product in enumerate(results[:2], 1):
                    print(f"      {j}. {product.get('title', 'N/A')[:50]}...")
                    print(f"         ¥{product.get('price', 'N/A'):,} - {product.get('shop', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Total products found across all queries: {total_found}")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_queries()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

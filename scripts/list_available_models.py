#!/usr/bin/env python3
"""
Quick script to list all available Gemini models for your API key.
Usage: python scripts/list_available_models.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from google import genai
except ImportError:
    print("ERROR: google-genai not installed")
    print("Please install: pip install google-genai")
    sys.exit(1)

# Get API key from environment
api_key = os.getenv('GENAI_API_KEY') or os.getenv('GOOGLE_API_KEY')
if not api_key:
    print("ERROR: GENAI_API_KEY or GOOGLE_API_KEY not set")
    sys.exit(1)

# Create client
try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    print(f"ERROR: Failed to create Gemini client: {e}")
    sys.exit(1)

print("Available Gemini models for your API key:\n")
print(f"{'Model Name':<50} {'Description':<50}")
print("=" * 100)

try:
    # List all available models using new SDK
    models = client.models.list()
    
    for model in models:
        name = model.name if hasattr(model, 'name') else str(model)
        description = model.display_name if hasattr(model, 'display_name') else ''
        if not description and hasattr(model, 'description'):
            description = model.description
        
        print(f"{name:<50} {description:<50}")
        
except Exception as e:
    print(f"ERROR listing models: {e}")
    print("\nTrying to test specific model names...")
    
    # Try specific common model names
    test_models = [
        'gemini-2.5-flash',
        'gemini-2.0-flash-exp', 
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-exp-1206'
    ]
    
    print("\nTesting specific model names:")
    for model_name in test_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents="test"
            )
            print(f"✓ {model_name}: WORKS")
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"✗ {model_name}: {error_msg}")


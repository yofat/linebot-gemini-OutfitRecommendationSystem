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
    import google.generativeai as genai
except ImportError:
    print("ERROR: google-generativeai not installed")
    sys.exit(1)

# Get API key from environment
api_key = os.getenv('GENAI_API_KEY') or os.getenv('GOOGLE_API_KEY')
if not api_key:
    print("ERROR: GENAI_API_KEY or GOOGLE_API_KEY not set")
    sys.exit(1)

# Configure SDK
genai.configure(api_key=api_key)

print("Available Gemini models for your API key:\n")
print(f"{'Model Name':<50} {'Supports':<30}")
print("=" * 80)

try:
    for model in genai.list_models():
        name = model.name
        # Check what methods are supported
        methods = []
        if hasattr(model, 'supported_generation_methods'):
            methods = model.supported_generation_methods
        elif hasattr(model, 'supported_methods'):
            methods = getattr(model, 'supported_methods', [])
        
        methods_str = ', '.join(methods) if methods else 'N/A'
        print(f"{name:<50} {methods_str:<30}")
        
except Exception as e:
    print(f"ERROR listing models: {e}")
    sys.exit(1)

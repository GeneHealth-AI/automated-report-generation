#!/usr/bin/env python3
"""
Check API configuration and help set up the correct environment variables
"""

import os

def check_api_configuration():
    """Check which APIs are configured and provide guidance"""
    
    print("🔍 Checking API Configuration\n")
    
    # Check OpenAI
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        print(f"✅ OPENAI_API_KEY: Set (ends with ...{openai_key[-4:]})")
    else:
        print("❌ OPENAI_API_KEY: Not set")
    
    # Check Gemini
    gemini_key = os.environ.get('GEMINI_API_KEY')
    if gemini_key:
        print(f"✅ GEMINI_API_KEY: Set (ends with ...{gemini_key[-4:]})")
    else:
        print("❌ GEMINI_API_KEY: Not set")
    
    # Check LLM Provider setting
    llm_provider = os.environ.get('LLM_PROVIDER', 'openai')
    print(f"🔧 LLM_PROVIDER: {llm_provider}")
    
    print("\n" + "=" * 60)
    print("Configuration Recommendations:")
    print("=" * 60)
    
    if not openai_key and not gemini_key:
        print("❌ No API keys found!")
        print("\nTo use OpenAI (recommended):")
        print("export OPENAI_API_KEY='your-openai-api-key'")
        print("export LLM_PROVIDER='openai'")
        print("\nTo use Google Gemini:")
        print("export GEMINI_API_KEY='your-gemini-api-key'")
        print("export LLM_PROVIDER='gemini'")
    
    elif openai_key and not gemini_key:
        print("✅ OpenAI configured - this is the recommended setup")
        if llm_provider != 'openai':
            print("💡 Consider setting: export LLM_PROVIDER='openai'")
    
    elif gemini_key and not openai_key:
        print("✅ Gemini configured")
        if llm_provider != 'gemini':
            print("💡 Consider setting: export LLM_PROVIDER='gemini'")
    
    else:
        print("✅ Both APIs configured")
        print(f"Current provider: {llm_provider}")
        print("You can switch between them using LLM_PROVIDER environment variable")
    
    print("\n" + "=" * 60)
    print("Current System Status:")
    print("=" * 60)
    
    if openai_key:
        print("🟢 OpenAI functions will work")
    else:
        print("🔴 OpenAI functions will NOT work")
    
    if gemini_key:
        print("🟢 Gemini functions will work")
    else:
        print("🔴 Gemini functions will NOT work")
    
    # Determine what will actually be used
    if llm_provider == 'openai' and openai_key:
        print(f"🎯 System will use: OpenAI")
    elif llm_provider == 'gemini' and gemini_key:
        print(f"🎯 System will use: Gemini")
    elif openai_key:
        print(f"🎯 System will use: OpenAI (fallback)")
    elif gemini_key:
        print(f"🎯 System will use: Gemini (fallback)")
    else:
        print(f"🚫 System will FAIL - no working API configured")

if __name__ == "__main__":
    check_api_configuration()
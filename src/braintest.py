import ollama

try:
    response = ollama.list()
    print("✅ Connection Successful! Friday is ready to think.")
    
    # Accessing 'model' instead of 'name'
    models = [m.model for m in response.models] 
    print(f"Models found: {models}")
    
    if 'phi4-mini:latest' in models or 'phi4-mini' in models:
        print("🚀 Phi4-Mini is ready. Friday has her brain!")
    else:
        print("⚠️ Phi4-Mini not found. Run 'ollama pull phi4-mini' in terminal.")
        
except Exception as e:
    print(f"❌ Connection Failed. Error: {e}")
    
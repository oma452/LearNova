#!/usr/bin/env python3

import subprocess
import time
import requests
import json
import sys

def start_server():
    """Start the FastAPI server in the background"""
    print("Starting server...")
    # Start the server using subprocess
    process = subprocess.Popen([
        'bash', '-c', 
        'cd /mnt/d/LearNova/LearNova && source ~/miniconda3/etc/profile.d/conda.sh && conda activate learnova && python -m uvicorn src.main:app --host 0.0.0.0 --port 8000'
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Wait for server to start
    print("Waiting for server to start...")
    time.sleep(15)
    
    return process

def test_endpoint():
    """Test the chat endpoint"""
    url = "http://localhost:8000/api/v1/students/chatbot/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjp7InVuaXF1ZV9pZCI6IjIyMDA5IiwidXNlcl90eXBlIjoic3R1ZGVudCJ9LCJleHAiOjE3NTgxNjkxOTEsImp0aSI6IjBiNTE5YmI0LTgwZmQtNGQ5ZS04M2ZiLTgyMGIxNTMzOTBhNSIsInJlZnJlc2giOmZhbHNlfQ.n_Tm8k0PNeE4Vx_gSkVTMMI0u1nJTRwf4N1lvPC3fwo"
    }
    data = {
        "message": "What is photosynthesis?",
        "session_id": "test_session_001"
    }
    
    try:
        print("Making request to endpoint...")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nParsed response:")
            print(json.dumps(result, indent=2))
        
        return response.status_code == 200
        
    except requests.exceptions.Timeout:
        print("Request timed out after 60 seconds")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Main test function"""
    print("=== Testing Chatbot Endpoint ===")
    
    # Start server
    server_process = start_server()
    
    try:
        # Test endpoint
        success = test_endpoint()
        
        if success:
            print("\n✅ Test completed successfully!")
        else:
            print("\n❌ Test failed!")
            
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    finally:
        # Clean up server process
        print("\nStopping server...")
        try:
            # Get server output
            output, _ = server_process.communicate(timeout=2)
            print("Server output:")
            print(output)
        except subprocess.TimeoutExpired:
            server_process.kill()
            output, _ = server_process.communicate()
            print("Server output (after kill):")
            print(output)
        
        print("Server stopped.")

if __name__ == "__main__":
    main()
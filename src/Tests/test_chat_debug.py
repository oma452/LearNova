#!/usr/bin/env python3
import requests
import json

def test_chat():
    url = "http://localhost:8000/api/v1/students/chatbot/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjp7ImlkIjoiOGMyNWZlYmQtMzE2NS00MjEwLWIzMGQtYjgwZmQ1YTUxNDM4IiwidW5pcXVlX2lkIjoiMjIwMDkiLCJlbWFpbCI6InN0MTMzLndhbGlkNUBtc2EuZWR1LmVnIiwibmFtZSI6IkFobWVkIFdhbGlkIHVwZGF0ZWQifSwiZXhwIjoxNzU4MDgzODQ5LCJqdGkiOiJhNjEwMTEyZC1lNzM3LTQ0NTktYjIzNC1iMjYwMDIyOWNlNDUiLCJyZWZyZXNoIjpmYWxzZX0.72C9RaHJiU0yVLfrBJ3flSgL6Dhgrz6AJlnHO9je7Xo"
    }
    data = {
        "message": "What is photosynthesis?",
        "session_id": "test_session_001"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nParsed response:")
            print(json.dumps(result, indent=2))
        
    except requests.exceptions.Timeout:
        print("Request timed out after 30 seconds")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_chat()
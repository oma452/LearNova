#!/usr/bin/env python3
"""
Test script for chatbot endpoint functionality.
"""

import asyncio
import aiohttp
import json
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_chatbot_endpoint():
    """Test the chatbot chat endpoint."""
    try:
        # Test data
        test_data = {
            "message": "Can you explain the concept of recursion in programming?"
        }
        
        # Headers (using student token)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyMjAwOSIsInJvbGUiOiJzdHVkZW50IiwiZXhwIjoxNzM3MDQ4ODQ2fQ.7Z8ZQsYOYA0kUtqJqw3a_lV4T8i72tkVzBM-a9dkOK8"
        }
        
        # Make request
        url = "http://localhost:8000/api/student/chatbot/chat"
        
        async with aiohttp.ClientSession() as session:
            logger.info(f"Making request to {url}")
            logger.info(f"Request data: {json.dumps(test_data, indent=2)}")
            
            async with session.post(url, json=test_data, headers=headers) as response:
                status = response.status
                response_text = await response.text()
                
                logger.info(f"Response Status: {status}")
                logger.info(f"Response Body: {response_text}")
                
                if status == 200:
                    try:
                        response_json = json.loads(response_text)
                        logger.info("✅ Chat endpoint successful!")
                        logger.info(f"Final response: {response_json.get('final_response', 'No final response')}")
                        return True
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response")
                        return False
                else:
                    logger.error(f"❌ Chat endpoint failed with status {status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        return False

async def main():
    """Run all tests."""
    logger.info("🚀 Starting chatbot endpoint tests...")
    
    success = await test_chatbot_endpoint()
    
    if success:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
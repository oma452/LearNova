#!/bin/bash
curl -X POST "http://localhost:8000/api/v1/students/chatbot/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwidXNlcl90eXBlIjoic3R1ZGVudCIsImlhdCI6MTczODAzMTk0MCwiZXhwIjoxNzM4MTE4MzQwfQ.ZrZQBP8sAYAJBhNajOjd_n0mE-iGwKKHHNhfXs5KUZ8" \
  -d '{"message": "What is photosynthesis?", "session_id": "test_session_001"}' \
  --max-time 30
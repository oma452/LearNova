#!/usr/bin/env bash
# Run from the root of your LearNova repo AFTER copying README.md, .gitignore,
# .env.example and alembic.ini from this folder into it.
set -e

# 1. Stop tracking files that should never be in the repo (keeps them on disk)
git rm --cached -q server.log 2>/dev/null || true
git rm -r --cached -q --ignore-unmatch celerybeat celerybeat-schedule
git rm -q --cached --ignore-unmatch .env.pgvector.example Docker/.env.example src/.env.example
git rm -q --cached --ignore-unmatch src/Chatbot/MCP/Servers/lesson_retrieval_server.py.backup
git rm -q --cached --ignore-unmatch PHASE2_IMPLEMENTATION_SUMMARY.py test_phase1_implementation.py test_phase2_implementation.py

# 2. Move ad-hoc test scripts into the Tests package
mkdir -p src/Tests
git mv test_chat_debug.py test_chatbot_endpoint.py test_chatbot_standalone.py \
       test_student_response_implementation.py src/Tests/ 2>/dev/null || true
mv test_chat.sh src/Tests/ 2>/dev/null || true

# 3. Stage everything and review
git add -A
git status --short
echo; echo "Review the list above, then:  git commit -m 'chore: clean up repo, add .env.example, rewrite README'"

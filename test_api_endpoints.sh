#!/bin/bash
# Test script for public catalogue API endpoints
# Run after starting the Django server

echo "=================================="
echo "Testing Public Catalogue API"
echo "=================================="
echo ""

BASE_URL="http://127.0.0.1:8000/api/v1"

echo "1️⃣  Testing GET /api/v1/public/courses/"
echo "   (Should return published courses without authentication)"
echo ""
curl -s -o /tmp/test1.json -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/courses/"
if [ -f /tmp/test1.json ]; then
    python3 -m json.tool /tmp/test1.json 2>/dev/null | head -50 || cat /tmp/test1.json
fi
echo ""
echo "---"
echo ""

echo "2️⃣  Testing GET /api/v1/public/courses/advanced-react-patterns/"
echo "   (Should return course detail by slug)"
echo ""
curl -s -o /tmp/test2.json -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/courses/advanced-react-patterns/"
if [ -f /tmp/test2.json ]; then
    python3 -m json.tool /tmp/test2.json 2>/dev/null | head -50 || cat /tmp/test2.json
fi
echo ""
echo "---"
echo ""

echo "3️⃣  Testing GET /api/v1/public/categories/"
echo "   (Should return active categories)"
echo ""
curl -s -o /tmp/test3.json -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/categories/"
if [ -f /tmp/test3.json ]; then
    python3 -m json.tool /tmp/test3.json 2>/dev/null | head -30 || cat /tmp/test3.json
fi
echo ""
echo "---"
echo ""

echo "4️⃣  Testing GET /api/v1/public/tags/"
echo "   (Should return all tags)"
echo ""
curl -s -o /tmp/test4.json -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/tags/"
if [ -f /tmp/test4.json ]; then
    python3 -m json.tool /tmp/test4.json 2>/dev/null | head -30 || cat /tmp/test4.json
fi
echo ""
echo "---"
echo ""

echo "5️⃣  Testing GET /api/v1/public/courses/?featured=true"
echo "   (Should filter featured courses)"
echo ""
curl -s -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/courses/?featured=true" | python3 -m json.tool 2>/dev/null | grep -E '"count"|"title"|"featured"' | head -10
echo ""
echo "---"
echo ""

echo "6️⃣  Testing GET /api/v1/public/courses/?category=1"
echo "   (Should filter by category)"
echo ""
curl -s -w "HTTP Status: %{http_code}\n" "$BASE_URL/public/courses/?category=1" | python3 -m json.tool 2>/dev/null | grep -E '"count"|"title"|"category"' | head -10
echo ""
echo "---"
echo ""

echo "✅ Tests Complete!"
echo ""
echo "All endpoints should return HTTP 200 without requiring authentication."

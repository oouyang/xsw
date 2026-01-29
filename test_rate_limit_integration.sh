#!/bin/bash
# Integration test for rate limiting
# Run this after starting the FastAPI server

echo "============================================================"
echo "RATE LIMITING INTEGRATION TEST"
echo "============================================================"
echo ""
echo "Prerequisites: FastAPI server should be running on localhost:8000"
echo ""

API_BASE="http://localhost:8000/xsw/api"

# Test 1: Check rate limit stats endpoint
echo "TEST 1: Checking rate limit stats endpoint..."
curl -s "${API_BASE}/admin/rate-limit/stats" | python3 -m json.tool
echo ""

# Test 2: Make rapid requests to trigger rate limiting
echo "TEST 2: Making 60 rapid requests to /health endpoint..."
echo "First 50 should be fast, 51-60 should have 1s delay each"
echo ""

START_TIME=$(date +%s)

for i in {1..60}; do
    if [ $i -eq 1 ] || [ $i -eq 25 ] || [ $i -eq 50 ] || [ $i -eq 51 ] || [ $i -eq 60 ]; then
        CURRENT_TIME=$(date +%s)
        ELAPSED=$((CURRENT_TIME - START_TIME))
        echo "Request $i (elapsed: ${ELAPSED}s)..."
        curl -s "${API_BASE}/health" > /dev/null
    else
        curl -s "${API_BASE}/health" > /dev/null
    fi
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

echo ""
echo "Total time for 60 requests: ${TOTAL_TIME}s"
echo "Expected: ~10s (first 50 fast, next 10 with 1s delay each)"
echo ""

# Test 3: Check updated stats
echo "TEST 3: Checking updated stats after requests..."
curl -s "${API_BASE}/admin/rate-limit/stats" | python3 -m json.tool
echo ""

echo "============================================================"
echo "INTEGRATION TEST COMPLETE"
echo "============================================================"
echo ""
echo "Manual verification:"
echo "1. Check logs for [RateLimit] messages showing delays"
echo "2. Verify total time is reasonable (~10-20s for 60 requests)"
echo "3. Verify stats show your IP with ~60 requests"
echo ""

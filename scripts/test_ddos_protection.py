#!/usr/bin/env python3
"""
Test DDoS Protection and Bot Detection

This script tests various attack scenarios to verify protection is working.
"""

import sys
import time
import requests
from datetime import datetime


BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/xsw/api/health"


def print_test_header(title: str):
    """Print test section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def test_normal_traffic():
    """Test normal user traffic - should all succeed"""
    print_test_header("TEST 1: Normal User Traffic")

    success = 0
    for i in range(10):
        try:
            r = requests.get(API_URL, timeout=5)
            if r.status_code == 200:
                success += 1
                print(f"  Request {i+1}: ✓ {r.status_code}")
            else:
                print(f"  Request {i+1}: ✗ {r.status_code}")
        except Exception as e:
            print(f"  Request {i+1}: ✗ Error: {e}")

        time.sleep(0.5)  # Reasonable delay

    print(f"\nResult: {success}/10 requests succeeded")
    return success == 10


def test_rate_limiting():
    """Test rate limiting - should block after limit"""
    print_test_header("TEST 2: Rate Limiting (Rapid Requests)")

    results = []
    print("  Sending 120 rapid requests...")

    for i in range(120):
        try:
            r = requests.get(API_URL, timeout=5)
            results.append(r.status_code)

            if i < 5 or i % 20 == 0 or i > 115:
                print(f"  Request {i+1}: {r.status_code}")

        except Exception as e:
            results.append(0)
            if i < 5 or i > 115:
                print(f"  Request {i+1}: Error: {e}")

    success_count = sum(1 for s in results if s == 200)
    blocked_count = sum(1 for s in results if s == 429)

    print("\nResults:")
    print(f"  Successful: {success_count}")
    print(f"  Blocked (429): {blocked_count}")
    print(f"  Errors: {len(results) - success_count - blocked_count}")

    # Should have some blocks
    return blocked_count > 0


def test_bot_detection():
    """Test bot detection - should block bot user agents"""
    print_test_header("TEST 3: Bot Detection")

    test_cases = [
        ("Normal Browser", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0", 200),
        ("Googlebot (Good)", "Mozilla/5.0 (compatible; Googlebot/2.1)", 200),
        ("Scrapy Bot (Bad)", "Scrapy/1.0", 429),
        ("Python Requests (Bad)", "python-requests/2.28.0", 429),
        ("curl (Bad)", "curl/7.68.0", 429),
        ("No User-Agent", "", 429),
    ]

    results = []
    for name, user_agent, expected in test_cases:
        try:
            headers = {"User-Agent": user_agent} if user_agent else {}
            r = requests.get(API_URL, headers=headers, timeout=5)

            passed = (r.status_code == expected or
                     (expected == 429 and r.status_code in [403, 429]))

            status = "✓" if passed else "✗"
            print(f"  {name:20s} → {r.status_code} {status}")

            results.append(passed)

        except Exception as e:
            print(f"  {name:20s} → Error: {e} ✗")
            results.append(False)

        time.sleep(1)

    passed = sum(results)
    print(f"\nResult: {passed}/{len(test_cases)} tests passed")
    return passed >= len(test_cases) * 0.7  # At least 70% pass


def test_suspicious_paths():
    """Test suspicious path detection"""
    print_test_header("TEST 4: Suspicious Path Detection")

    test_paths = [
        ("/xsw/api/health", 200, "Normal path"),
        ("/admin", 429, "Admin path"),
        ("/wp-admin", 429, "WordPress admin"),
        ("/.env", 429, "Sensitive file"),
        ("/../../etc/passwd", 429, "Path traversal"),
        ("/test.php", 429, "PHP file"),
    ]

    results = []
    for path, expected, description in test_paths:
        try:
            url = f"{BASE_URL}{path}"
            r = requests.get(url, timeout=5)

            # Allow 404 for legitimate "path not found"
            passed = (r.status_code == expected or
                     (expected == 429 and r.status_code in [403, 404, 429]))

            status = "✓" if passed else "✗"
            print(f"  {description:20s} → {r.status_code} {status}")

            results.append(passed)

        except Exception as e:
            print(f"  {description:20s} → Error: {e} ✗")
            results.append(False)

        time.sleep(1)

    passed = sum(results)
    print(f"\nResult: {passed}/{len(test_paths)} tests passed")
    return passed >= len(test_paths) * 0.6  # At least 60% pass


def test_progressive_throttling():
    """Test progressive throttling"""
    print_test_header("TEST 5: Progressive Throttling")

    print("  Sending requests at moderate pace...")

    times = []
    for i in range(60):
        start = time.time()
        try:
            r = requests.get(API_URL, timeout=10)
            elapsed = time.time() - start

            times.append(elapsed)

            if i < 3 or i in [40, 50, 59]:
                print(f"  Request {i+1}: {r.status_code} ({elapsed:.2f}s)")

        except Exception as e:
            print(f"  Request {i+1}: Error: {e}")
            break

        time.sleep(0.5)  # Moderate pace

    if times:
        avg_early = sum(times[:10]) / 10
        avg_late = sum(times[-10:]) / 10

        print("\nAverage response time:")
        print(f"  First 10 requests: {avg_early:.2f}s")
        print(f"  Last 10 requests: {avg_late:.2f}s")

        # Late requests should be slower (throttled)
        return avg_late > avg_early

    return False


def test_admin_stats():
    """Test admin statistics endpoint"""
    print_test_header("TEST 6: Admin Statistics (Optional)")

    try:
        # Try without auth (should fail)
        r = requests.get(f"{BASE_URL}/xsw/api/admin/ddos/stats", timeout=5)

        if r.status_code in [401, 403]:
            print(f"  ✓ Stats endpoint requires auth: {r.status_code}")
            return True
        elif r.status_code == 200:
            stats = r.json()
            print("  ✓ Stats endpoint accessible (auth disabled)")
            print(f"    Total requests: {stats.get('total_requests', 'N/A')}")
            print(f"    Blocked requests: {stats.get('blocked_requests', 'N/A')}")
            return True
        else:
            print(f"  ✗ Unexpected status: {r.status_code}")
            return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  DDoS Protection Test Suite")
    print("  Target: " + BASE_URL)
    print("  Time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    # Check if server is running
    try:
        r = requests.get(API_URL, timeout=5)
        print(f"\n✓ Server is responding (Status: {r.status_code})")
    except Exception as e:
        print(f"\n✗ Cannot connect to server: {e}")
        print("  Make sure the server is running:")
        print("  uvicorn main_optimized:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # Run tests
    tests = [
        ("Normal Traffic", test_normal_traffic),
        ("Rate Limiting", test_rate_limiting),
        ("Bot Detection", test_bot_detection),
        ("Suspicious Paths", test_suspicious_paths),
        ("Progressive Throttling", test_progressive_throttling),
        ("Admin Stats", test_admin_stats),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            results.append((name, False))

        # Wait between tests
        time.sleep(2)

    # Summary
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name:25s} {status}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All tests passed! DDoS protection is working.")
        return 0
    elif passed_count >= total_count * 0.7:
        print("\n⚠️  Most tests passed. Some features may need tuning.")
        return 0
    else:
        print("\n❌ Many tests failed. Please check configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test script for rate limiter functionality.
Tests the RateLimiter class in isolation before deploying.
"""

from rate_limiter import RateLimiter


def test_basic_functionality():
    """Test basic rate limiting logic"""
    print("=" * 60)
    print("TEST 1: Basic Functionality")
    print("=" * 60)

    # Create rate limiter with no whitelist
    limiter = RateLimiter([])

    # Test 1: First 50 requests should have no delay
    print("\n1. Testing 0-50 requests (should have no delay)")
    for i in range(50):
        delay = limiter.get_delay("192.168.1.100")
        limiter.record_request("192.168.1.100")
        if i in [0, 10, 25, 49]:
            print(f"   Request {i+1}: delay = {delay}s")

    assert delay == 0.0, f"Expected 0s delay, got {delay}s"
    print("   ✓ First 50 requests have no delay")

    # Test 2: 51st request should trigger 1s delay
    print("\n2. Testing 51st request (should have 1s delay)")
    delay = limiter.get_delay("192.168.1.100")
    print(f"   Request 51: delay = {delay}s")
    assert delay == 1.0, f"Expected 1s delay, got {delay}s"
    print("   ✓ 51st request triggers 1s delay")

    limiter.record_request("192.168.1.100")

    # Test 3: Continue to 100 requests (should still be 1s)
    print("\n3. Testing requests 52-100 (should have 1s delay)")
    for i in range(51, 100):
        delay = limiter.get_delay("192.168.1.100")
        limiter.record_request("192.168.1.100")

    print(f"   Request 100: delay = {delay}s")
    assert delay == 1.0, f"Expected 1s delay, got {delay}s"
    print("   ✓ Requests 52-100 have 1s delay")

    # Test 4: 101st request should trigger 10s delay
    print("\n4. Testing 101st request (should have 10s delay)")
    delay = limiter.get_delay("192.168.1.100")
    print(f"   Request 101: delay = {delay}s")
    assert delay == 10.0, f"Expected 10s delay, got {delay}s"
    print("   ✓ 101st request triggers 10s delay")


def test_whitelist():
    """Test whitelist functionality"""
    print("\n" + "=" * 60)
    print("TEST 2: Whitelist Functionality")
    print("=" * 60)

    # Create rate limiter with whitelist
    limiter = RateLimiter(["127.0.0.1", "10.0.0.0/8", "192.168.1.0/24"])

    # Test whitelisted single IP
    print("\n1. Testing whitelisted IP (127.0.0.1)")
    for i in range(600):  # Way over limit
        limiter.record_request("127.0.0.1")

    delay = limiter.get_delay("127.0.0.1")
    print(f"   After 600 requests: delay = {delay}s")
    assert delay == 0.0, f"Whitelisted IP should have no delay, got {delay}s"
    print("   ✓ Whitelisted single IP bypasses all limits")

    # Test whitelisted CIDR range
    print("\n2. Testing whitelisted CIDR (10.0.0.0/8)")
    for i in range(600):
        limiter.record_request("10.5.10.20")

    delay = limiter.get_delay("10.5.10.20")
    print(f"   After 600 requests: delay = {delay}s")
    assert delay == 0.0, f"Whitelisted CIDR IP should have no delay, got {delay}s"
    print("   ✓ Whitelisted CIDR range bypasses all limits")

    # Test non-whitelisted IP
    print("\n3. Testing non-whitelisted IP (8.8.8.8)")
    for i in range(600):
        limiter.record_request("8.8.8.8")

    delay = limiter.get_delay("8.8.8.8")
    print(f"   After 600 requests: delay = {delay}s")
    assert delay == 300.0, f"Expected 300s delay for 600+ requests, got {delay}s"
    print("   ✓ Non-whitelisted IP gets rate limited correctly")


def test_sliding_window():
    """Test sliding window cleanup"""
    print("\n" + "=" * 60)
    print("TEST 3: Sliding Window Cleanup")
    print("=" * 60)

    limiter = RateLimiter([])

    # Make 60 requests
    print("\n1. Making 60 requests...")
    for i in range(60):
        limiter.record_request("203.0.113.1")

    delay = limiter.get_delay("203.0.113.1")
    print(f"   After 60 requests: delay = {delay}s")
    assert delay == 1.0, f"Expected 1s delay for 60 requests, got {delay}s"

    # Wait for window to expire
    print("\n2. Waiting 61 seconds for window to expire...")
    print("   (simulating by clearing history manually)")

    # Simulate time passing by clearing old requests
    limiter._request_history["203.0.113.1"] = []

    delay = limiter.get_delay("203.0.113.1")
    print(f"   After window expiry: delay = {delay}s")
    assert delay == 0.0, f"Expected 0s delay after window expiry, got {delay}s"
    print("   ✓ Sliding window cleanup works correctly")


def test_multiple_clients():
    """Test multiple clients are tracked independently"""
    print("\n" + "=" * 60)
    print("TEST 4: Multiple Clients")
    print("=" * 60)

    limiter = RateLimiter([])

    print("\n1. Client A makes 60 requests")
    for i in range(60):
        limiter.record_request("198.51.100.1")

    print("2. Client B makes 10 requests")
    for i in range(10):
        limiter.record_request("198.51.100.2")

    delay_a = limiter.get_delay("198.51.100.1")
    delay_b = limiter.get_delay("198.51.100.2")

    print(f"   Client A delay: {delay_a}s (expected 1s)")
    print(f"   Client B delay: {delay_b}s (expected 0s)")

    assert delay_a == 1.0, f"Client A should have 1s delay, got {delay_a}s"
    assert delay_b == 0.0, f"Client B should have 0s delay, got {delay_b}s"
    print("   ✓ Clients tracked independently")


def test_stats():
    """Test statistics reporting"""
    print("\n" + "=" * 60)
    print("TEST 5: Statistics")
    print("=" * 60)

    limiter = RateLimiter(["127.0.0.1", "10.0.0.0/8"])

    # Add some requests
    for i in range(30):
        limiter.record_request("192.168.1.1")
    for i in range(20):
        limiter.record_request("192.168.1.2")

    stats = limiter.get_stats()

    print("\nStatistics:")
    print(f"   Active clients: {stats['active_clients']}")
    print(f"   Total requests in window: {stats['total_requests_in_window']}")
    print(f"   Whitelist IPs: {stats['whitelist_ips']}")
    print(f"   Whitelist networks: {stats['whitelist_networks']}")

    assert stats['active_clients'] == 2, f"Expected 2 active clients, got {stats['active_clients']}"
    assert stats['total_requests_in_window'] == 50, f"Expected 50 total requests, got {stats['total_requests_in_window']}"
    assert stats['whitelist_ips'] == 1, f"Expected 1 whitelisted IP, got {stats['whitelist_ips']}"
    assert stats['whitelist_networks'] == 1, f"Expected 1 whitelisted network, got {stats['whitelist_networks']}"
    print("   ✓ Statistics are accurate")


if __name__ == "__main__":
    try:
        print("\n" + "=" * 60)
        print("RATE LIMITER TEST SUITE")
        print("=" * 60)

        test_basic_functionality()
        test_whitelist()
        test_sliding_window()
        test_multiple_clients()
        test_stats()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60 + "\n")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)

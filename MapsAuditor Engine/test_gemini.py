"""
NETWORK DIAGNOSTIC SCRIPT
Tests for:
- ISP blocking Google services
- Corporate/Government firewall
- Antivirus SSL inspection
- Network-level restrictions
"""

import os
import sys
import socket
import ssl
import subprocess
import urllib.request
import urllib.error
import json
import time

# ============================================================
# TEST 1: Basic Internet Connectivity
# ============================================================
print("\n" + "=" * 60)
print("TEST 1: Basic Internet Connectivity")
print("=" * 60)

def test_basic_internet():
    """Test if you can reach basic websites"""
    sites = [
        ("Google", "https://www.google.com"),
        ("Cloudflare", "https://www.cloudflare.com"),
        ("Microsoft", "https://www.microsoft.com"),
        ("Amazon", "https://www.amazon.com"),
    ]
    
    results = []
    for name, url in sites:
        try:
            response = urllib.request.urlopen(url, timeout=5)
            print(f"   ✅ {name}: Reachable (Status: {response.getcode()})")
            results.append(True)
        except Exception as e:
            print(f"   ❌ {name}: NOT Reachable ({str(e)[:50]})")
            results.append(False)
    
    return any(results)

has_internet = test_basic_internet()

# TEST 2: DNS Resolution for Google APIs
print("\n" + "=" * 60)
print("TEST 2: DNS Resolution for Google Services")
print("=" * 60)

def test_dns_resolution():
    """Test DNS resolution for Google domains"""
    domains = [
        "google.com",
        "generativelanguage.googleapis.com",
        "www.googleapis.com",
        "googleapis.com",
    ]
    
    results = []
    for domain in domains:
        try:
            ip = socket.gethostbyname(domain)
            print(f"    {domain}: Resolves to {ip}")
            results.append(True)
        except Exception as e:
            print(f"    {domain}: DNS Resolution Failed ({str(e)})")
            results.append(False)
    
    return any(results)

has_dns = test_dns_resolution()

# TEST 3: SSL/TLS Connection Test
print("\n" + "=" * 60)
print("TEST 3: SSL/TLS Connection Test")
print("=" * 60)

def test_ssl_connection():
    """Test SSL connection to Google servers"""
    host = "generativelanguage.googleapis.com"
    port = 443
    
    try:
        print(f"   Connecting to {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # Try SSL handshake
        context = ssl.create_default_context()
        ssl_sock = context.wrap_socket(sock, server_hostname=host)
        
        certificate = ssl_sock.getpeercert()
        print(f"   ✅ SSL Connection Successful")
        print(f"   ✅ Certificate Issuer: {dict(certificate).get('issuer', 'N/A')}")
        ssl_sock.close()
        return True
        
    except ssl.SSLError as e:
        print(f"   ❌ SSL Error: {e}")
        print("   → Antivirus SSL inspection or outdated certificates")
        return False
    except socket.timeout:
        print("   ❌ Connection Timeout - Firewall likely blocking")
        return False
    except ConnectionResetError:
        print("   ❌ Connection Reset - ISP or firewall blocking")
        return False
    except Exception as e:
        print(f"   ❌ Connection Failed: {e}")
        return False

has_ssl = test_ssl_connection()

# ============================================================
# TEST 4: HTTP/HTTPS Request to Gemini
# ============================================================
print("\n" + "=" * 60)
print("TEST 4: Gemini API Request (Direct)")
print("=" * 60)

def test_gemini_connection():
    """Direct test to Gemini API"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key=dummy_key"
    
    try:
        print(f"   Testing connection to Gemini API...")
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        
        # This will fail with 401/403 but tells us if connection works
        response = urllib.request.urlopen(req, timeout=10)
        print(f"   ⚠️ Unexpected response: {response.getcode()}")
        return True
        
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            print(f"   ✅ Connection works (Authentication required, not a network issue)")
            return True
        else:
            print(f"   ❌ Connection failed: HTTP {e.code}")
            return False
    except urllib.error.URLError as e:
        print(f"   ❌ Connection failed: {str(e.reason)}")
        if "timeout" in str(e).lower():
            print("   → Likely firewall blocking")
        elif "reset" in str(e).lower():
            print("   → Connection forcibly closed - ISP/AV blocking")
        return False
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False

has_gemini_connection = test_gemini_connection()

# ============================================================
# TEST 5: Check for Proxy
# ============================================================
print("\n" + "=" * 60)
print("TEST 5: Proxy Detection")
print("=" * 60)

def test_proxy_detection():
    """Check if a proxy is being used"""
    proxy_vars = [
        "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY",
        "http_proxy", "https_proxy", "ftp_proxy",
        "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"
    ]
    
    found_proxies = []
    for var in proxy_vars:
        value = os.environ.get(var)
        if value:
            found_proxies.append(f"{var}={value}")
    
    if found_proxies:
        print("   ⚠️ Proxy found in environment variables:")
        for proxy in found_proxies:
            print(f"      - {proxy}")
    else:
        print("   ✅ No proxy environment variables detected")
    
    return len(found_proxies) > 0

has_proxy = test_proxy_detection()

# ============================================================
# TEST 6: Traceroute to Google (Optional)
# ============================================================
print("\n" + "=" * 60)
print("TEST 6: Network Path Check (traceroute)")
print("=" * 60)

def test_traceroute():
    """Run traceroute to Google"""
    try:
        # Try tracert (Windows) or traceroute (Mac/Linux)
        try:
            result = subprocess.run(
                ["tracert", "-d", "-h", "10", "google.com"],
                capture_output=True,
                text=True,
                timeout=30
            )
            command = "tracert"
        except FileNotFoundError:
            try:
                result = subprocess.run(
                    ["traceroute", "-n", "-m", "10", "google.com"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                command = "traceroute"
            except FileNotFoundError:
                print("   ❌ tracert/traceroute not available")
                return False
        
        lines = result.stdout.split('\n')
        print(f"   First 5 hops ({command} google.com):")
        for line in lines[:5]:
            if line.strip():
                print(f"      {line.strip()}")
        
        if "Request timed out" in result.stdout or "* * *" in result.stdout:
            print("   ⚠️ Timeouts detected - firewall may be blocking")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("   ❌ Traceroute timed out")
        return False
    except Exception as e:
        print(f"   ❌ Traceroute failed: {e}")
        return False

test_traceroute()

# ============================================================
# TEST 7: Check for VPN/Cloudflare WARP
# ============================================================
print("\n" + "=" * 60)
print("TEST 7: VPN/Proxy Detection")
print("=" * 60)

def test_vpn_detection():
    """Check if VPN is active"""
    try:
        # Check IP via Cloudflare
        response = urllib.request.urlopen("https://1.1.1.1/cdn-cgi/trace", timeout=5)
        data = response.read().decode()
        
        for line in data.split('\n'):
            if line.startswith("warp="):
                if line == "warp=on":
                    print("   ✅ Cloudflare WARP is active")
                    return True
                else:
                    print("   ℹ️ Cloudflare WARP is off")
            if line.startswith("colo="):
                print(f"   📍 Cloudflare datacenter: {line.replace('colo=', '')}")
        
        # Check IP location
        response = urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5)
        data = json.loads(response.read().decode())
        print(f"   📍 Your IP: {data.get('ip', 'Unknown')}")
        
        # Check if IP is from known VPN provider (basic check)
        response = urllib.request.urlopen("https://ipinfo.io/json", timeout=5)
        data = json.loads(response.read().decode())
        org = data.get('org', '').lower()
        if any(vpn_provider in org for vpn_provider in ['cloudflare', 'aws', 'azure', 'digitalocean', 'vpn', 'proxy']):
            print(f"   ℹ️ IP may be from: {org}")
        
    except Exception as e:
        print(f"   ⚠️ Could not check VPN status: {e}")

test_vpn_detection()

# ============================================================
# SUMMARY & DIAGNOSIS
# ============================================================
print("\n" + "=" * 60)
print("DIAGNOSIS SUMMARY")
print("=" * 60)

print("\n🔍 What the tests indicate:\n")

if not has_internet:
    print("   ❌ Your network has no internet connectivity.")
    print("      → Check your internet connection.")
    
elif not has_dns:
    print("   ❌ DNS resolution failed for Google domains.")
    print("      → Your ISP or network may be blocking Google services.")
    print("      → Try using a VPN or changing DNS to 8.8.8.8")

elif has_dns and not has_gemini_connection:
    print("   ❌ Gemini API is reachable at DNS level but connection fails.")
    if has_proxy:
        print("      → Your network has a proxy configured.")
        print("      → The proxy may be blocking or filtering traffic.")
    else:
        print("      → Your ISP or firewall is actively blocking Google API traffic.")
        print("      → Antivirus with SSL inspection may be the cause.")
        print("      → Government/Corporate firewall restrictions.")

elif has_dns and has_gemini_connection:
    print("   ✅ Network seems to be working correctly.")
    print("      → Your issue may be with the specific API key or code.")
    print("      → Try re-generating your Gemini API key.")

else:
    print("   ⚠️ Mixed results. Please check the individual test outputs above.")

print("\n🔧 RECOMMENDATIONS:")

if not has_gemini_connection:
    print("\n   1. TRY A VPN (Fastest fix):")
    print("      - Cloudflare WARP (free, fastest): https://1.1.1.1/")
    print("      - ProtonVPN (free): https://protonvpn.com/")
    print("      - Windscribe (free 10GB): https://windscribe.com/")
    
    print("\n   2. DISABLE SSL INSPECTION:")
    print("      - Temporarily disable antivirus")
    print("      - Check firewall settings")
    print("      - Disable HTTPS scanning in antivirus")
    
    print("\n   3. CHANGE DNS SERVER:")
    print("      - Google DNS: 8.8.8.8 and 8.8.4.4")
    print("      - Cloudflare DNS: 1.1.1.1 and 1.0.0.1")
    
    print("\n   4. DEPLOY TO CLOUD VPS:")
    print("      - Digital Ocean $6/month")
    print("      - Server won't have these restrictions")

else:
    print("\n   ✅ Your network seems to allow Google API access.")
    print("   → Check your API key and code.")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)

# ============================================================
# SAVE RESULTS
# ============================================================
print("\n📁 Saving diagnostic report to 'network_diagnostic.txt'")

with open("network_diagnostic.txt", "w") as f:
    f.write("=" * 60 + "\n")
    f.write("NETWORK DIAGNOSTIC REPORT\n")
    f.write("=" * 60 + "\n\n")
    f.write(f"Basic Internet: {'✅' if has_internet else '❌'}\n")
    f.write(f"DNS Resolution: {'✅' if has_dns else '❌'}\n")
    f.write(f"SSL Connection: {'✅' if has_ssl else '❌'}\n")
    f.write(f"Gemini API: {'✅' if has_gemini_connection else '❌'}\n")
    f.write(f"Proxy Detected: {'⚠️' if has_proxy else '✅'}\n\n")
    f.write("=" * 60 + "\n")
    f.write("RECOMMENDATIONS:\n")
    f.write("=" * 60 + "\n")
    
    if not has_gemini_connection:
        f.write("\n1. Try Cloudflare WARP (free): https://1.1.1.1/\n")
        f.write("2. Try ProtonVPN (free): https://protonvpn.com/\n")
        f.write("3. Disable antivirus SSL inspection temporarily\n")
        f.write("4. Change DNS to 8.8.8.8 and 8.8.4.4\n")
        f.write("5. Deploy to a cloud VPS ($6/month)\n")

print("✅ Report saved to network_diagnostic.txt")

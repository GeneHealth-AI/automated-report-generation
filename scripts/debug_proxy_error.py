#!/usr/bin/env python3
"""
Debug script to identify the source of the 'proxies' parameter error
"""

import os
import sys
import traceback

def check_environment_variables():
    """Check for proxy-related environment variables"""
    print("🔍 Checking Environment Variables:")
    print("=" * 50)
    
    proxy_vars = [
        'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
        'NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy'
    ]
    
    found_proxy_vars = []
    for var in proxy_vars:
        value = os.environ.get(var)
        if value:
            found_proxy_vars.append(f"{var}={value}")
            print(f"⚠️  {var}: {value}")
    
    if not found_proxy_vars:
        print("✅ No proxy environment variables found")
    
    return found_proxy_vars

def test_requests_library():
    """Test requests library for proxy issues"""
    print("\n🔍 Testing Requests Library:")
    print("=" * 50)
    
    try:
        import requests
        print(f"✅ Requests version: {requests.__version__}")
        
        # Test simple request
        print("🔄 Testing simple HTTP request...")
        response = requests.get("https://httpbin.org/get", timeout=10)
        print(f"✅ Simple request successful: {response.status_code}")
        
        # Test with explicit proxies=None
        print("🔄 Testing request with proxies=None...")
        response = requests.get("https://httpbin.org/get", proxies=None, timeout=10)
        print(f"✅ Request with proxies=None successful: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"❌ Requests error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return False

def test_boto3_clients():
    """Test boto3 client creation"""
    print("\n🔍 Testing Boto3 Clients:")
    print("=" * 50)
    
    try:
        import boto3
        print(f"✅ Boto3 version: {boto3.__version__}")
        
        # Test S3 client creation
        print("🔄 Creating S3 client...")
        s3 = boto3.client('s3')
        print("✅ S3 client created successfully")
        
        # Test ECS client creation
        print("🔄 Creating ECS client...")
        ecs = boto3.client('ecs')
        print("✅ ECS client created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Boto3 error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return False

def test_report_generator():
    """Test ReportGenerator imports and basic functionality"""
    print("\n🔍 Testing ReportGenerator:")
    print("=" * 50)
    
    try:
        print("🔄 Importing ReportGenerator...")
        from ReportGenerator import Report
        print("✅ ReportGenerator imported successfully")
        
        print("🔄 Creating Report instance...")
        report = Report()
        print("✅ Report instance created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ ReportGenerator error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return False

def test_block_generator():
    """Test BlockGenerator imports"""
    print("\n🔍 Testing BlockGenerator:")
    print("=" * 50)
    
    try:
        print("🔄 Importing block_generator...")
        from block_generator import ReportBlockGenerator
        print("✅ block_generator imported successfully")
        
        print("🔄 Creating ReportBlockGenerator instance...")
        generator = ReportBlockGenerator(
            blocks_path='./blocks',
            block_configs={'custom_prompt': 'test'}
        )
        print("✅ ReportBlockGenerator instance created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ BlockGenerator error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return False

def main():
    """Run all diagnostic tests"""
    print("🔧 Proxy Error Diagnostic Tool")
    print("=" * 60)
    
    # Check environment variables
    proxy_vars = check_environment_variables()
    
    # Test various components
    tests = [
        ("Requests Library", test_requests_library),
        ("Boto3 Clients", test_boto3_clients),
        ("ReportGenerator", test_report_generator),
        ("BlockGenerator", test_block_generator),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ {test_name} test crashed: {str(e)}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 DIAGNOSTIC SUMMARY")
    print("=" * 60)
    
    if proxy_vars:
        print("⚠️  PROXY ENVIRONMENT VARIABLES FOUND:")
        for var in proxy_vars:
            print(f"   {var}")
        print("\n💡 Try unsetting these variables:")
        for var in proxy_vars:
            var_name = var.split('=')[0]
            print(f"   unset {var_name}")
    
    print(f"\n📊 TEST RESULTS:")
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"   {test_name}: {status}")
    
    failed_tests = [name for name, passed in results.items() if not passed]
    if failed_tests:
        print(f"\n🚨 FAILED TESTS: {', '.join(failed_tests)}")
        print("The 'proxies' error is likely coming from one of these components.")
    else:
        print(f"\n🎉 All tests passed! The 'proxies' error might be intermittent or environment-specific.")

if __name__ == "__main__":
    main()
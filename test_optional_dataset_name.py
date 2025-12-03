#!/usr/bin/env python3
"""
Test script for optional dataset_name functionality
"""

import requests
import json
import io

API_BASE_URL = "http://localhost:8000"
TEST_USER_ID = "test_user_123"

def create_test_csv():
    """Create a simple test CSV file"""
    csv_content = "name,age,city\nJohn,25,New York\nJane,30,Los Angeles\nBob,35,Chicago"
    return io.BytesIO(csv_content.encode('utf-8'))

def test_upload_without_name():
    """Test uploading a dataset without providing a name"""
    print("🧪 Testing dataset upload without name...")
    
    # Create test file
    test_file = create_test_csv()
    
    # Upload without name
    files = {
        'file': ('test_data.csv', test_file, 'text/csv')
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/{TEST_USER_ID}",
            files=files
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Success!")
            print(f"   Dataset ID: {result.get('dataset_id', 'N/A')}")
            print(f"   Dataset Name: {result.get('name', 'N/A')}")
            print(f"   Version: {result.get('version', 'N/A')}")
            return result
        else:
            print(f"   ❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def test_upload_with_name():
    """Test uploading a dataset with a custom name"""
    print("\n🧪 Testing dataset upload with custom name...")
    
    # Create test file
    test_file = create_test_csv()
    
    # Upload with custom name
    files = {
        'file': ('test_data.csv', test_file, 'text/csv')
    }
    
    data = {
        'name': 'My Custom Dataset Name'
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/{TEST_USER_ID}",
            files=files,
            data=data
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Success!")
            print(f"   Dataset ID: {result.get('dataset_id', 'N/A')}")
            print(f"   Dataset Name: {result.get('name', 'N/A')}")
            print(f"   Version: {result.get('version', 'N/A')}")
            return result
        else:
            print(f"   ❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def test_multiple_uploads():
    """Test multiple uploads to verify auto-naming counter"""
    print("\n🧪 Testing multiple uploads to verify auto-naming...")
    
    results = []
    
    for i in range(3):
        print(f"\n   Upload {i+1}:")
        
        # Create test file
        test_file = create_test_csv()
        
        files = {
            'file': (f'test_data_{i+1}.csv', test_file, 'text/csv')
        }
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/datasets/upload/{TEST_USER_ID}",
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Dataset Name: {result.get('name', 'N/A')}")
                results.append(result)
            else:
                print(f"   ❌ Failed: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    return results

def test_folder_upload_without_name():
    """Test folder upload without name"""
    print("\n🧪 Testing folder upload without name...")
    
    # Create a simple zip file (this is a simplified test)
    # In a real scenario, you'd create an actual zip file
    zip_content = b"PK\x03\x04"  # Minimal zip header
    
    files = {
        'zip_file': ('test_folder.zip', io.BytesIO(zip_content), 'application/zip')
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/folder/{TEST_USER_ID}",
            files=files
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Success!")
            print(f"   Dataset ID: {result.get('dataset_id', 'N/A')}")
            print(f"   Dataset Name: {result.get('name', 'N/A')}")
            print(f"   Version: {result.get('version', 'N/A')}")
            return result
        else:
            print(f"   ❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def main():
    """Run all tests"""
    print("Optional Dataset Name Test Suite")
    print("=" * 50)
    
    # Test 1: Upload without name
    result1 = test_upload_without_name()
    
    # Test 2: Upload with custom name
    result2 = test_upload_with_name()
    
    # Test 3: Multiple uploads to test counter
    results = test_multiple_uploads()
    
    # Test 4: Folder upload without name
    result3 = test_folder_upload_without_name()
    
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"   Single upload without name: {'✅' if result1 else '❌'}")
    print(f"   Single upload with name: {'✅' if result2 else '❌'}")
    print(f"   Multiple uploads: {'✅' if len(results) > 0 else '❌'}")
    print(f"   Folder upload without name: {'✅' if result3 else '❌'}")
    
    if result1:
        print(f"\n🎯 Expected auto-generated name pattern: user_uploaded_dataset_*")
        print(f"   First upload name: {result1.get('name', 'N/A')}")
    
    if results:
        print(f"\n🔢 Auto-naming counter test:")
        for i, result in enumerate(results):
            print(f"   Upload {i+1}: {result.get('name', 'N/A')}")

if __name__ == "__main__":
    main()

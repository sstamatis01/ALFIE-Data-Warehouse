<<<<<<< HEAD
#!/usr/bin/env python3
"""
Test script to verify that dataset_id is now optional in upload endpoints
"""

import requests
import json
import io

API_BASE_URL = "http://localhost:8000"

def test_upload_without_dataset_id():
    """Test uploading a dataset without providing dataset_id"""
    try:
        # Create a simple test file
        test_content = "name,age,city\nJohn,25,New York\nJane,30,Los Angeles"
        test_file = io.BytesIO(test_content.encode())
        
        # Test data
        files = {
            'file': ('test.csv', test_file, 'text/csv')
        }
        data = {
            'name': 'Test Dataset',
            'description': 'Test dataset without dataset_id',
            'tags': 'test,optional'
        }
        
        print("Testing upload without dataset_id...")
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/test_user",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Generated dataset_id: {result.get('dataset_id')}")
            return result.get('dataset_id')
        else:
            print(f"❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_upload_with_dataset_id():
    """Test uploading a dataset with provided dataset_id"""
    try:
        # Create a simple test file
        test_content = "name,age,city\nBob,35,Chicago\nAlice,28,Boston"
        test_file = io.BytesIO(test_content.encode())
        
        # Test data
        files = {
            'file': ('test2.csv', test_file, 'text/csv')
        }
        data = {
            'dataset_id': 'custom-dataset-id-123',
            'name': 'Test Dataset with Custom ID',
            'description': 'Test dataset with custom dataset_id',
            'tags': 'test,custom'
        }
        
        print("\nTesting upload with custom dataset_id...")
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/test_user",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Used dataset_id: {result.get('dataset_id')}")
            return result.get('dataset_id')
        else:
            print(f"❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_api_health():
    """Test if the API is accessible"""
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ API is accessible")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to API at {API_BASE_URL}")
        return False

def main():
    """Main test function"""
    print("Testing Optional Dataset ID Feature")
    print("=" * 40)
    
    # Test API health
    if not test_api_health():
        print("Please start the API server first:")
        print("  docker-compose up")
        return
    
    # Test upload without dataset_id
    auto_generated_id = test_upload_without_dataset_id()
    
    # Test upload with dataset_id
    custom_id = test_upload_with_dataset_id()
    
    print("\n" + "=" * 40)
    print("Test Summary:")
    print(f"Auto-generated dataset_id: {auto_generated_id}")
    print(f"Custom dataset_id: {custom_id}")
    
    if auto_generated_id and custom_id:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

if __name__ == "__main__":
    main()
=======
#!/usr/bin/env python3
"""
Test script to verify that dataset_id is now optional in upload endpoints
"""

import requests
import json
import io

API_BASE_URL = "http://localhost:8000"

def test_upload_without_dataset_id():
    """Test uploading a dataset without providing dataset_id"""
    try:
        # Create a simple test file
        test_content = "name,age,city\nJohn,25,New York\nJane,30,Los Angeles"
        test_file = io.BytesIO(test_content.encode())
        
        # Test data
        files = {
            'file': ('test.csv', test_file, 'text/csv')
        }
        data = {
            'name': 'Test Dataset',
            'description': 'Test dataset without dataset_id',
            'tags': 'test,optional'
        }
        
        print("Testing upload without dataset_id...")
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/test_user",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Generated dataset_id: {result.get('dataset_id')}")
            return result.get('dataset_id')
        else:
            print(f"❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_upload_with_dataset_id():
    """Test uploading a dataset with provided dataset_id"""
    try:
        # Create a simple test file
        test_content = "name,age,city\nBob,35,Chicago\nAlice,28,Boston"
        test_file = io.BytesIO(test_content.encode())
        
        # Test data
        files = {
            'file': ('test2.csv', test_file, 'text/csv')
        }
        data = {
            'dataset_id': 'custom-dataset-id-123',
            'name': 'Test Dataset with Custom ID',
            'description': 'Test dataset with custom dataset_id',
            'tags': 'test,custom'
        }
        
        print("\nTesting upload with custom dataset_id...")
        response = requests.post(
            f"{API_BASE_URL}/datasets/upload/test_user",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Used dataset_id: {result.get('dataset_id')}")
            return result.get('dataset_id')
        else:
            print(f"❌ Failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_api_health():
    """Test if the API is accessible"""
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ API is accessible")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to API at {API_BASE_URL}")
        return False

def main():
    """Main test function"""
    print("Testing Optional Dataset ID Feature")
    print("=" * 40)
    
    # Test API health
    if not test_api_health():
        print("Please start the API server first:")
        print("  docker-compose up")
        return
    
    # Test upload without dataset_id
    auto_generated_id = test_upload_without_dataset_id()
    
    # Test upload with dataset_id
    custom_id = test_upload_with_dataset_id()
    
    print("\n" + "=" * 40)
    print("Test Summary:")
    print(f"Auto-generated dataset_id: {auto_generated_id}")
    print(f"Custom dataset_id: {custom_id}")
    
    if auto_generated_id and custom_id:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

if __name__ == "__main__":
    main()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

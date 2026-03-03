#!/usr/bin/env python3
"""
Debug script to test GraphDB connection step by step
"""

import requests
import json

API_BASE_URL = "http://localhost:8000"
GRAPHDB_CONFIG_ID = "68f75db5ebc917f006e16fb9"  # ETD-Hub Knowledge Graph config

def test_api_connection():
    """Test if the API is accessible"""
    print("1. Testing API connection...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ API is accessible")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False

def test_graphdb_health():
    """Test GraphDB service health"""
    print("\n2. Testing GraphDB service health...")
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/health")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ GraphDB service: {result['status']}")
            print(f"   Message: {result['message']}")
            return True
        else:
            print(f"❌ GraphDB health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ GraphDB health check error: {e}")
        return False

def test_graphdb_config():
    """Test if our GraphDB configuration exists"""
    print("\n3. Testing GraphDB configuration...")
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs/{GRAPHDB_CONFIG_ID}")
        if response.status_code == 200:
            config = response.json()
            print(f"✅ Configuration found: {config['name']}")
            print(f"   Repository: {config['repository_name']}")
            print(f"   Status: {config['status']}")
            return True
        else:
            print(f"❌ Configuration not found: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Configuration check error: {e}")
        return False

def test_graphdb_connection():
    """Test GraphDB connection"""
    print("\n4. Testing GraphDB connection...")
    try:
        response = requests.post(f"{API_BASE_URL}/graphdb/configs/{GRAPHDB_CONFIG_ID}/test")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Connection test completed")
            print(f"   Success: {result['success']}")
            print(f"   Message: {result['message']}")
            print(f"   SELECT endpoint: {'✅' if result['select_endpoint_accessible'] else '❌'}")
            print(f"   UPDATE endpoint: {'✅' if result['update_endpoint_accessible'] else '❌'}")
            print(f"   Repository exists: {'✅' if result['repository_exists'] else '❌'}")
            return result['success']
        else:
            print(f"❌ Connection test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Connection test error: {e}")
        return False

def test_simple_query():
    """Test a simple SPARQL query"""
    print("\n5. Testing simple SPARQL query...")
    try:
        # Simple query to check if repository exists
        query_data = {
            "config_id": GRAPHDB_CONFIG_ID,
            "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 1",
            "query_type": "SELECT"
        }
        
        response = requests.post(
            f"{API_BASE_URL}/graphdb/query",
            json=query_data
        )
        
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Query executed successfully")
            print(f"   Success: {result.get('success', 'Unknown')}")
            if result.get('error'):
                print(f"   Error: {result['error']}")
            return result.get('success', False)
        else:
            print(f"❌ Query failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Query test error: {e}")
        return False

def main():
    """Main debug function"""
    print("GraphDB Connection Debug Script")
    print("=" * 40)
    
    # Test each step
    api_ok = test_api_connection()
    if not api_ok:
        print("\n❌ Cannot proceed - API not accessible")
        return
    
    graphdb_health_ok = test_graphdb_health()
    if not graphdb_health_ok:
        print("\n❌ Cannot proceed - GraphDB service not healthy")
        return
    
    config_ok = test_graphdb_config()
    if not config_ok:
        print("\n❌ Cannot proceed - GraphDB configuration not found")
        return
    
    connection_ok = test_graphdb_connection()
    if not connection_ok:
        print("\n❌ Cannot proceed - GraphDB connection failed")
        print("\n🔧 Possible solutions:")
        print("   1. Create the repository in GraphDB web interface")
        print("   2. Check GraphDB is running: docker compose ps")
        print("   3. Access GraphDB at: http://localhost:7200")
        return
    
    query_ok = test_simple_query()
    if not query_ok:
        print("\n❌ Cannot proceed - SPARQL queries not working")
        return
    
    print("\n🎉 All tests passed! GraphDB is ready to use.")
    print("\nNext steps:")
    print("   1. Run the full ETD-Hub example script")
    print("   2. Create repositories in GraphDB web interface")
    print("   3. Start inserting semantic data")

if __name__ == "__main__":
    main()

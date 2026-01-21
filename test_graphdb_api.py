#!/usr/bin/env python3
"""
Test script for GraphDB API endpoints
"""

import requests
import json
import time

API_BASE_URL = "http://localhost:8000"

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

def test_graphdb_health():
    """Test GraphDB service health"""
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/health")
        print(f"GraphDB Health Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ GraphDB health check failed: {e}")
        return False

def create_graphdb_config():
    """Create a test GraphDB configuration"""
    try:
        config_data = {
            "name": "Test GraphDB Config",
            "description": "Test configuration for GraphDB",
            "select_endpoint": "http://localhost:7200/repositories/test-repo",
            "update_endpoint": "http://localhost:7200/repositories/test-repo/statements",
            "username": "admin",
            "password": "admin",
            "repository_name": "test-repo",
            "timeout": 30,
            "max_retries": 3
        }
        
        response = requests.post(
            f"{API_BASE_URL}/graphdb/configs?created_by=test_user",
            json=config_data
        )
        
        print(f"Create Config Status: {response.status_code}")
        if response.status_code == 201:
            result = response.json()
            print(f"✅ Created GraphDB configuration: {result['id']}")
            return result['id']
        else:
            print(f"❌ Failed to create config: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error creating GraphDB config: {e}")
        return None

def get_graphdb_configs():
    """Get all GraphDB configurations"""
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs")
        print(f"Get Configs Status: {response.status_code}")
        if response.status_code == 200:
            configs = response.json()
            print(f"✅ Found {len(configs)} GraphDB configurations")
            return configs
        else:
            print(f"❌ Failed to get configs: {response.text}")
            return []
    except Exception as e:
        print(f"❌ Error getting GraphDB configs: {e}")
        return []

def test_graphdb_connection(config_id):
    """Test GraphDB connection"""
    try:
        response = requests.post(f"{API_BASE_URL}/graphdb/configs/{config_id}/test")
        print(f"Test Connection Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Connection test completed: {result['success']}")
            print(f"   SELECT endpoint accessible: {result['select_endpoint_accessible']}")
            print(f"   UPDATE endpoint accessible: {result['update_endpoint_accessible']}")
            print(f"   Repository exists: {result['repository_exists']}")
            print(f"   Authentication successful: {result['authentication_successful']}")
            return result['success']
        else:
            print(f"❌ Connection test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
        return False

def get_query_examples(config_id):
    """Get query examples for GraphDB configuration"""
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs/{config_id}/query-examples")
        print(f"Get Query Examples Status: {response.status_code}")
        if response.status_code == 200:
            examples = response.json()
            print("✅ Query examples retrieved:")
            print(f"   SELECT examples: {len(examples['select_examples'])}")
            print(f"   UPDATE examples: {len(examples['update_examples'])}")
            return examples
        else:
            print(f"❌ Failed to get query examples: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error getting query examples: {e}")
        return None

def execute_sparql_query(config_id, query, query_type="SELECT"):
    """Execute a SPARQL query"""
    try:
        query_data = {
            "config_id": config_id,
            "query": query,
            "query_type": query_type
        }
        
        response = requests.post(
            f"{API_BASE_URL}/graphdb/query",
            json=query_data
        )
        
        print(f"Execute Query Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Query executed successfully")
            print(f"   Execution time: {result['execution_time']:.3f}s")
            print(f"   Query type: {result['query_type']}")
            if result.get('data'):
                print(f"   Data: {json.dumps(result['data'], indent=2)[:200]}...")
            return result
        else:
            print(f"❌ Query execution failed: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error executing query: {e}")
        return None

def delete_graphdb_config(config_id):
    """Delete GraphDB configuration"""
    try:
        response = requests.delete(f"{API_BASE_URL}/graphdb/configs/{config_id}")
        print(f"Delete Config Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Deleted GraphDB configuration: {result['message']}")
            return True
        else:
            print(f"❌ Failed to delete config: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error deleting GraphDB config: {e}")
        return False

def main():
    """Main test function"""
    print("Testing GraphDB API")
    print("=" * 50)
    
    # Test API health
    if not test_api_health():
        print("Please start the API server first:")
        print("  docker-compose up")
        return
    
    # Test GraphDB health
    print("\n" + "-" * 30)
    print("Testing GraphDB Service Health")
    test_graphdb_health()
    
    # Create GraphDB configuration
    print("\n" + "-" * 30)
    print("Creating GraphDB Configuration")
    config_id = create_graphdb_config()
    
    if not config_id:
        print("❌ Cannot proceed without a valid configuration")
        return
    
    # Get configurations
    print("\n" + "-" * 30)
    print("Getting GraphDB Configurations")
    configs = get_graphdb_configs()
    
    # Test connection (this will likely fail without a real GraphDB instance)
    print("\n" + "-" * 30)
    print("Testing GraphDB Connection")
    print("Note: This will likely fail without a real GraphDB instance running")
    connection_success = test_graphdb_connection(config_id)
    
    # Get query examples
    print("\n" + "-" * 30)
    print("Getting Query Examples")
    examples = get_query_examples(config_id)
    
    # Try to execute a simple query (will likely fail without real GraphDB)
    if examples:
        print("\n" + "-" * 30)
        print("Executing Sample SPARQL Query")
        print("Note: This will likely fail without a real GraphDB instance running")
        sample_query = examples['select_examples'][0]['query']
        execute_sparql_query(config_id, sample_query, "SELECT")
    
    # Clean up - delete the test configuration
    print("\n" + "-" * 30)
    print("Cleaning Up")
    delete_graphdb_config(config_id)
    
    print("\n" + "=" * 50)
    print("GraphDB API Test Complete!")
    print("\nTo test with a real GraphDB instance:")
    print("1. Install and start GraphDB")
    print("2. Create a repository")
    print("3. Update the configuration with real endpoints")
    print("4. Run the connection test")

if __name__ == "__main__":
    main()

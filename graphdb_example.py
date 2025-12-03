#!/usr/bin/env python3
"""
Example script demonstrating GraphDB API usage
"""

import requests
import json
import time

API_BASE_URL = "http://localhost:8000"

def main():
    """Demonstrate GraphDB API usage"""
    print("GraphDB API Usage Example")
    print("=" * 40)
    
    # Example 1: Create a GraphDB configuration
    print("\n1. Creating GraphDB Configuration")
    config_data = {
        "name": "Example GraphDB",
        "description": "Example configuration for demonstration",
        "select_endpoint": "http://localhost:7200/repositories/example",
        "update_endpoint": "http://localhost:7200/repositories/example/statements",
        "username": "admin",
        "password": "admin",
        "repository_name": "example",
        "timeout": 30,
        "max_retries": 3
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/graphdb/configs?created_by=example_user",
            json=config_data
        )
        
        if response.status_code == 201:
            config = response.json()
            config_id = config["id"]
            print(f"✅ Created configuration: {config['name']} (ID: {config_id})")
        else:
            print(f"❌ Failed to create configuration: {response.text}")
            return
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Please start the server first.")
        return
    
    # Example 2: Test the connection
    print("\n2. Testing GraphDB Connection")
    try:
        response = requests.post(f"{API_BASE_URL}/graphdb/configs/{config_id}/test")
        if response.status_code == 200:
            result = response.json()
            print(f"Connection test result: {result['success']}")
            print(f"  SELECT endpoint: {'✅' if result['select_endpoint_accessible'] else '❌'}")
            print(f"  UPDATE endpoint: {'✅' if result['update_endpoint_accessible'] else '❌'}")
            print(f"  Repository exists: {'✅' if result['repository_exists'] else '❌'}")
        else:
            print(f"❌ Connection test failed: {response.text}")
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
    
    # Example 3: Get query examples
    print("\n3. Getting Query Examples")
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs/{config_id}/query-examples")
        if response.status_code == 200:
            examples = response.json()
            print(f"✅ Retrieved {len(examples['select_examples'])} SELECT examples")
            print(f"✅ Retrieved {len(examples['update_examples'])} UPDATE examples")
            
            # Show first SELECT example
            if examples['select_examples']:
                first_example = examples['select_examples'][0]
                print(f"\nFirst SELECT example:")
                print(f"  Name: {first_example['name']}")
                print(f"  Query: {first_example['query']}")
                print(f"  Description: {first_example['description']}")
        else:
            print(f"❌ Failed to get examples: {response.text}")
    except Exception as e:
        print(f"❌ Error getting examples: {e}")
    
    # Example 4: Execute a simple SELECT query
    print("\n4. Executing SPARQL Query")
    try:
        query_data = {
            "config_id": config_id,
            "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 5",
            "query_type": "SELECT"
        }
        
        response = requests.post(
            f"{API_BASE_URL}/graphdb/query",
            json=query_data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Query executed successfully")
            print(f"  Execution time: {result['execution_time']:.3f}s")
            print(f"  Success: {result['success']}")
            if result.get('error'):
                print(f"  Error: {result['error']}")
        else:
            print(f"❌ Query execution failed: {response.text}")
    except Exception as e:
        print(f"❌ Error executing query: {e}")
    
    # Example 5: Get all configurations
    print("\n5. Listing All Configurations")
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs")
        if response.status_code == 200:
            configs = response.json()
            print(f"✅ Found {len(configs)} configurations:")
            for config in configs:
                print(f"  - {config['name']} (ID: {config['id']}, Status: {config['status']})")
        else:
            print(f"❌ Failed to get configurations: {response.text}")
    except Exception as e:
        print(f"❌ Error getting configurations: {e}")
    
    # Example 6: Clean up - delete the configuration
    print("\n6. Cleaning Up")
    try:
        response = requests.delete(f"{API_BASE_URL}/graphdb/configs/{config_id}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ {result['message']}")
        else:
            print(f"❌ Failed to delete configuration: {response.text}")
    except Exception as e:
        print(f"❌ Error deleting configuration: {e}")
    
    print("\n" + "=" * 40)
    print("Example completed!")
    print("\nNote: Some operations may fail if GraphDB is not running.")
    print("To test with a real GraphDB instance:")
    print("1. Install GraphDB: https://www.ontotext.com/products/graphdb/")
    print("2. Start GraphDB and create a repository")
    print("3. Update the endpoint URLs in the configuration")
    print("4. Run this example again")

if __name__ == "__main__":
    main()

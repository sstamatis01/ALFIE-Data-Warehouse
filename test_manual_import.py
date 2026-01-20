<<<<<<< HEAD
#!/usr/bin/env python3
"""
Test script to manually import ETD-Hub data and see detailed error messages
"""

import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"

def test_manual_import():
    """Test manual import with detailed error handling"""
    try:
        # Read the JSON file
        with open('exported_models.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded JSON data with keys: {list(data.keys())}")
        
        # Test with just themes first
        test_data = {
            "Theme": data["Theme"][:2]  # Just first 2 themes for testing
        }
        
        logger.info(f"Testing with {len(test_data['Theme'])} themes")
        
        # Try the import-data endpoint
        url = f"{API_BASE_URL}/etd-hub/import/import-data"
        
        payload = {
            "data": test_data,
            "clear_existing": True
        }
        
        logger.info("Sending request to API...")
        response = requests.post(url, json=payload)
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Import successful!")
            logger.info(f"Results: {result}")
        else:
            logger.error(f"❌ Import failed: {response.status_code}")
            logger.error(f"Error response: {response.text}")
            
            # Try to parse error details
            try:
                error_data = response.json()
                logger.error(f"Error details: {error_data}")
            except:
                logger.error(f"Raw error response: {response.text}")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")

def test_api_health():
    """Test API health and ETD-Hub endpoints"""
    try:
        # Test health endpoint
        health_response = requests.get(f"{API_BASE_URL}/health")
        logger.info(f"Health check: {health_response.status_code}")
        
        # Test ETD-Hub overview stats
        stats_response = requests.get(f"{API_BASE_URL}/etd-hub/stats/overview")
        logger.info(f"Stats endpoint: {stats_response.status_code}")
        if stats_response.status_code == 200:
            stats = stats_response.json()
            logger.info(f"Current stats: {stats}")
        
        # Test themes endpoint
        themes_response = requests.get(f"{API_BASE_URL}/etd-hub/themes")
        logger.info(f"Themes endpoint: {themes_response.status_code}")
        if themes_response.status_code == 200:
            themes = themes_response.json()
            logger.info(f"Current themes count: {len(themes)}")
        
    except Exception as e:
        logger.error(f"❌ API health test failed: {e}")

def main():
    """Main function"""
    logger.info("ETD-Hub Manual Import Test")
    logger.info("=" * 40)
    
    # Test API health first
    test_api_health()
    
    logger.info("\n" + "=" * 40)
    
    # Test manual import
    test_manual_import()

if __name__ == "__main__":
    main()
=======
#!/usr/bin/env python3
"""
Test script to manually import ETD-Hub data and see detailed error messages
"""

import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"

def test_manual_import():
    """Test manual import with detailed error handling"""
    try:
        # Read the JSON file
        with open('exported_models.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded JSON data with keys: {list(data.keys())}")
        
        # Test with just themes first
        test_data = {
            "Theme": data["Theme"][:2]  # Just first 2 themes for testing
        }
        
        logger.info(f"Testing with {len(test_data['Theme'])} themes")
        
        # Try the import-data endpoint
        url = f"{API_BASE_URL}/etd-hub/import/import-data"
        
        payload = {
            "data": test_data,
            "clear_existing": True
        }
        
        logger.info("Sending request to API...")
        response = requests.post(url, json=payload)
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Import successful!")
            logger.info(f"Results: {result}")
        else:
            logger.error(f"❌ Import failed: {response.status_code}")
            logger.error(f"Error response: {response.text}")
            
            # Try to parse error details
            try:
                error_data = response.json()
                logger.error(f"Error details: {error_data}")
            except:
                logger.error(f"Raw error response: {response.text}")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")

def test_api_health():
    """Test API health and ETD-Hub endpoints"""
    try:
        # Test health endpoint
        health_response = requests.get(f"{API_BASE_URL}/health")
        logger.info(f"Health check: {health_response.status_code}")
        
        # Test ETD-Hub overview stats
        stats_response = requests.get(f"{API_BASE_URL}/etd-hub/stats/overview")
        logger.info(f"Stats endpoint: {stats_response.status_code}")
        if stats_response.status_code == 200:
            stats = stats_response.json()
            logger.info(f"Current stats: {stats}")
        
        # Test themes endpoint
        themes_response = requests.get(f"{API_BASE_URL}/etd-hub/themes")
        logger.info(f"Themes endpoint: {themes_response.status_code}")
        if themes_response.status_code == 200:
            themes = themes_response.json()
            logger.info(f"Current themes count: {len(themes)}")
        
    except Exception as e:
        logger.error(f"❌ API health test failed: {e}")

def main():
    """Main function"""
    logger.info("ETD-Hub Manual Import Test")
    logger.info("=" * 40)
    
    # Test API health first
    test_api_health()
    
    logger.info("\n" + "=" * 40)
    
    # Test manual import
    test_manual_import()

if __name__ == "__main__":
    main()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

#!/usr/bin/env python3
"""
Script to upload ETD-Hub data via the API (works with Docker setup)
"""

import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"  # Update if your API is running on a different port

def upload_json_file(json_file_path: str, clear_existing: bool = True):
    """Upload JSON file to the API for import"""
    try:
        # Read the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded data from {json_file_path}")
        
        # Upload via API endpoint
        url = f"{API_BASE_URL}/etd-hub/import/import-data"
        
        payload = {
            "data": data,
            "clear_existing": clear_existing
        }
        
        logger.info("Uploading data to API...")
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Data uploaded successfully!")
            logger.info(f"Results: {result['results']}")
            logger.info(f"Total imported: {result['total_imported']}")
            return True
        else:
            logger.error(f"❌ Upload failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            return False
            
    except FileNotFoundError:
        logger.error(f"❌ File not found: {json_file_path}")
        return False
    except json.JSONDecodeError:
        logger.error(f"❌ Invalid JSON file: {json_file_path}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Could not connect to API at {API_BASE_URL}")
        logger.error("Make sure the API server is running (docker-compose up)")
        return False
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        return False

def upload_json_file_direct(json_file_path: str, clear_existing: bool = True):
    """Upload JSON file directly as file upload"""
    try:
        url = f"{API_BASE_URL}/etd-hub/import/upload-json"
        
        with open(json_file_path, 'rb') as f:
            files = {'file': (json_file_path, f, 'application/json')}
            data = {'clear_existing': clear_existing}
            
            logger.info("Uploading JSON file to API...")
            response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Data uploaded successfully!")
            logger.info(f"Results: {result['results']}")
            logger.info(f"Total imported: {result['total_imported']}")
            return True
        else:
            logger.error(f"❌ Upload failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            return False
            
    except FileNotFoundError:
        logger.error(f"❌ File not found: {json_file_path}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Could not connect to API at {API_BASE_URL}")
        logger.error("Make sure the API server is running (docker-compose up)")
        return False
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        return False

def test_api_connection():
    """Test if the API is accessible"""
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            logger.info("✅ API is accessible")
            return True
        else:
            logger.error(f"❌ API health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Could not connect to API at {API_BASE_URL}")
        return False

def main():
    """Main function"""
    json_file_path = "exported_models.json"
    
    logger.info("ETD-Hub Data Upload Script")
    logger.info("=" * 40)
    
    # Test API connection
    if not test_api_connection():
        logger.error("Please start the API server first:")
        logger.error("  docker-compose up")
        return
    
    # Try direct file upload first
    logger.info("Attempting direct file upload...")
    if upload_json_file_direct(json_file_path, clear_existing=True):
        return
    
    # Fallback to JSON data upload
    logger.info("Falling back to JSON data upload...")
    if upload_json_file(json_file_path, clear_existing=True):
        return
    
    logger.error("❌ All upload methods failed")

if __name__ == "__main__":
    main()

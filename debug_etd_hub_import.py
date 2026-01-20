<<<<<<< HEAD
#!/usr/bin/env python3
"""
Debug script to check the JSON structure and import process
"""

import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_json_structure(json_file_path: str):
    """Debug the JSON file structure"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info("=== JSON File Structure Debug ===")
        logger.info(f"Top-level keys: {list(data.keys())}")
        
        for key, value in data.items():
            if isinstance(value, list):
                logger.info(f"{key}: {len(value)} items")
                if value:  # If list is not empty
                    logger.info(f"  First item keys: {list(value[0].keys())}")
                    logger.info(f"  First item sample: {value[0]}")
            else:
                logger.info(f"{key}: {type(value)} - {value}")
        
        logger.info("=== End Debug ===")
        
        return data
        
    except Exception as e:
        logger.error(f"Error reading JSON file: {e}")
        return None

def test_import_logic(data):
    """Test the import logic with the actual data"""
    logger.info("=== Testing Import Logic ===")
    
    # Test themes
    if 'Theme' in data:
        themes = data['Theme']
        logger.info(f"Found {len(themes)} themes")
        if themes:
            logger.info(f"First theme: {themes[0]}")
    else:
        logger.info("No 'Theme' key found")
    
    # Test questions
    if 'Question' in data:
        questions = data['Question']
        logger.info(f"Found {len(questions)} questions")
        if questions:
            logger.info(f"First question: {questions[0]}")
    else:
        logger.info("No 'Question' key found")
    
    # Test answers
    if 'Answer' in data:
        answers = data['Answer']
        logger.info(f"Found {len(answers)} answers")
        if answers:
            logger.info(f"First answer: {answers[0]}")
    else:
        logger.info("No 'Answer' key found")
    
    # Test votes
    if 'Vote' in data:
        votes = data['Vote']
        logger.info(f"Found {len(votes)} votes")
        if votes:
            logger.info(f"First vote: {votes[0]}")
    else:
        logger.info("No 'Vote' key found")
    
    # Test experts
    if 'Expert' in data:
        experts = data['Expert']
        logger.info(f"Found {len(experts)} experts")
        if experts:
            logger.info(f"First expert: {experts[0]}")
    else:
        logger.info("No 'Expert' key found")
    
    # Test documents
    if 'Document' in data:
        documents = data['Document']
        logger.info(f"Found {len(documents)} documents")
        if documents:
            logger.info(f"First document: {documents[0]}")
    else:
        logger.info("No 'Document' key found")

def main():
    """Main function"""
    json_file_path = "exported_models.json"
    
    logger.info("ETD-Hub JSON Structure Debug")
    logger.info("=" * 40)
    
    # Debug JSON structure
    data = debug_json_structure(json_file_path)
    
    if data:
        # Test import logic
        test_import_logic(data)
    else:
        logger.error("Could not read JSON file")

if __name__ == "__main__":
    main()
=======
#!/usr/bin/env python3
"""
Debug script to check the JSON structure and import process
"""

import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_json_structure(json_file_path: str):
    """Debug the JSON file structure"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info("=== JSON File Structure Debug ===")
        logger.info(f"Top-level keys: {list(data.keys())}")
        
        for key, value in data.items():
            if isinstance(value, list):
                logger.info(f"{key}: {len(value)} items")
                if value:  # If list is not empty
                    logger.info(f"  First item keys: {list(value[0].keys())}")
                    logger.info(f"  First item sample: {value[0]}")
            else:
                logger.info(f"{key}: {type(value)} - {value}")
        
        logger.info("=== End Debug ===")
        
        return data
        
    except Exception as e:
        logger.error(f"Error reading JSON file: {e}")
        return None

def test_import_logic(data):
    """Test the import logic with the actual data"""
    logger.info("=== Testing Import Logic ===")
    
    # Test themes
    if 'Theme' in data:
        themes = data['Theme']
        logger.info(f"Found {len(themes)} themes")
        if themes:
            logger.info(f"First theme: {themes[0]}")
    else:
        logger.info("No 'Theme' key found")
    
    # Test questions
    if 'Question' in data:
        questions = data['Question']
        logger.info(f"Found {len(questions)} questions")
        if questions:
            logger.info(f"First question: {questions[0]}")
    else:
        logger.info("No 'Question' key found")
    
    # Test answers
    if 'Answer' in data:
        answers = data['Answer']
        logger.info(f"Found {len(answers)} answers")
        if answers:
            logger.info(f"First answer: {answers[0]}")
    else:
        logger.info("No 'Answer' key found")
    
    # Test votes
    if 'Vote' in data:
        votes = data['Vote']
        logger.info(f"Found {len(votes)} votes")
        if votes:
            logger.info(f"First vote: {votes[0]}")
    else:
        logger.info("No 'Vote' key found")
    
    # Test experts
    if 'Expert' in data:
        experts = data['Expert']
        logger.info(f"Found {len(experts)} experts")
        if experts:
            logger.info(f"First expert: {experts[0]}")
    else:
        logger.info("No 'Expert' key found")
    
    # Test documents
    if 'Document' in data:
        documents = data['Document']
        logger.info(f"Found {len(documents)} documents")
        if documents:
            logger.info(f"First document: {documents[0]}")
    else:
        logger.info("No 'Document' key found")

def main():
    """Main function"""
    json_file_path = "exported_models.json"
    
    logger.info("ETD-Hub JSON Structure Debug")
    logger.info("=" * 40)
    
    # Debug JSON structure
    data = debug_json_structure(json_file_path)
    
    if data:
        # Test import logic
        test_import_logic(data)
    else:
        logger.error("Could not read JSON file")

if __name__ == "__main__":
    main()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

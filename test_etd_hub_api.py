#!/usr/bin/env python3
"""
Test script to verify ETD-Hub API endpoints
"""

import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000/etd-hub"

def test_api_endpoints():
    """Test the ETD-Hub API endpoints"""
    
    print("Testing ETD-Hub API endpoints...")
    
    # Test 1: Get overview statistics
    try:
        response = requests.get(f"{BASE_URL}/stats/overview")
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Overview stats: {stats}")
        else:
            print(f"❌ Failed to get overview stats: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting overview stats: {e}")
    
    # Test 2: Get themes
    try:
        response = requests.get(f"{BASE_URL}/themes")
        if response.status_code == 200:
            themes = response.json()
            print(f"✅ Found {len(themes)} themes")
            if themes:
                print(f"   First theme: {themes[0]['name']}")
        else:
            print(f"❌ Failed to get themes: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting themes: {e}")
    
    # Test 3: Get experts
    try:
        response = requests.get(f"{BASE_URL}/experts")
        if response.status_code == 200:
            experts = response.json()
            print(f"✅ Found {len(experts)} experts")
            if experts:
                print(f"   First expert: {experts[0]['area_of_expertise']}")
        else:
            print(f"❌ Failed to get experts: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting experts: {e}")
    
    # Test 4: Get questions
    try:
        response = requests.get(f"{BASE_URL}/questions")
        if response.status_code == 200:
            questions = response.json()
            print(f"✅ Found {len(questions)} questions")
            if questions:
                print(f"   First question: {questions[0]['title']}")
        else:
            print(f"❌ Failed to get questions: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting questions: {e}")
    
    # Test 5: Get answers
    try:
        response = requests.get(f"{BASE_URL}/answers")
        if response.status_code == 200:
            answers = response.json()
            print(f"✅ Found {len(answers)} answers")
            if answers:
                print(f"   First answer: {answers[0]['description'][:100]}...")
        else:
            print(f"❌ Failed to get answers: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting answers: {e}")
    
    # Test 6: Get votes
    try:
        response = requests.get(f"{BASE_URL}/votes/1/1")  # This might not exist
        if response.status_code == 200:
            vote = response.json()
            print(f"✅ Found vote: {vote}")
        elif response.status_code == 404:
            print("✅ Vote endpoint working (no vote found for expert 1, answer 1)")
        else:
            print(f"❌ Failed to get vote: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting vote: {e}")

if __name__ == "__main__":
    test_api_endpoints()

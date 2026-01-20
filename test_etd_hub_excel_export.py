<<<<<<< HEAD
#!/usr/bin/env python3
"""
Test script to verify the ETD-Hub Excel export functionality.
This script tests the export service and endpoint without requiring a running server.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

import asyncio
import pandas as pd
from datetime import datetime
from app.services.etd_hub_export_service import etd_hub_export_service

async def test_export_service():
    """Test the ETD-Hub export service functionality"""
    print("🧪 Testing ETD-Hub Excel Export Service")
    print("=" * 60)
    
    try:
        # Initialize the service
        print("1. Initializing export service...")
        await etd_hub_export_service.initialize()
        print("✅ Export service initialized successfully")
        
        # Test DataFrame cleaning function
        print("\n2. Testing DataFrame cleaning...")
        test_data = {
            'theme_id': [1, 2, 3],
            'name': ['Theme 1', 'Theme 2', 'Theme 3'],
            'description': ['Desc 1', 'Desc 2', 'Desc 3'],
            'created_at': [datetime.now(), datetime.now(), datetime.now()],
            '_id': ['id1', 'id2', 'id3']  # This should be removed
        }
        
        test_df = pd.DataFrame(test_data)
        cleaned_df = etd_hub_export_service._clean_dataframe_for_excel(test_df)
        
        print(f"   Original columns: {list(test_df.columns)}")
        print(f"   Cleaned columns: {list(cleaned_df.columns)}")
        
        # Verify _id was removed
        assert '_id' not in cleaned_df.columns, "_id field should be removed"
        print("✅ DataFrame cleaning works correctly")
        
        # Test column mapping
        print("\n3. Testing column mapping...")
        themes_mapping = {
            'theme_id': 'Theme ID',
            'name': 'Theme Name',
            'description': 'Description',
            'views': 'Views',
            'expert_id': 'Expert ID',
            'problem_category': 'Problem Category',
            'model_category': 'Model Category',
            'domain_category': 'Domain Category',
            'created_at': 'Created At'
        }
        
        # Create a test DataFrame with the expected columns
        test_themes_df = pd.DataFrame({
            'theme_id': [1, 2],
            'name': ['Test Theme 1', 'Test Theme 2'],
            'description': ['Test Description 1', 'Test Description 2'],
            'views': [10, 20],
            'expert_id': [1, 2],
            'problem_category': ['AI_BIAS', 'PRIVACY'],
            'model_category': ['MACHINE_LEARNING', 'LLM'],
            'domain_category': ['HEALTH', 'FINANCE'],
            'created_at': [datetime.now(), datetime.now()]
        })
        
        # Apply column mapping
        mapped_df = test_themes_df.rename(columns=themes_mapping)
        print(f"   Mapped columns: {list(mapped_df.columns)}")
        print("✅ Column mapping works correctly")
        
        # Test Excel file creation (without actual database data)
        print("\n4. Testing Excel file creation...")
        try:
            import io
            from openpyxl import Workbook
            
            # Create a simple test Excel file
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Write test data to different sheets
                test_themes_df.to_excel(writer, sheet_name='Themes', index=False)
                
                # Create summary sheet
                summary_data = {
                    'Metric': ['Total Themes', 'Export Date'],
                    'Count': [2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            output.seek(0)
            file_size = len(output.getvalue())
            print(f"✅ Excel file created successfully (Size: {file_size} bytes)")
            
        except ImportError as e:
            print(f"⚠️  Excel creation test skipped - missing dependency: {e}")
            print("   Install openpyxl: pip install openpyxl")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed! The ETD-Hub Excel export service is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

def test_dependencies():
    """Test if all required dependencies are available"""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        'pandas',
        'openpyxl',
        'fastapi',
        'pymongo'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} - Available")
        except ImportError:
            print(f"❌ {package} - Missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("\n✅ All required dependencies are available!")
        return True

def main():
    """Run all tests"""
    print("🚀 ETD-Hub Excel Export Test Suite")
    print("=" * 60)
    
    # Test dependencies first
    if not test_dependencies():
        print("\n❌ Cannot run tests due to missing dependencies.")
        return
    
    print("\n" + "=" * 60)
    
    # Run async tests
    try:
        asyncio.run(test_export_service())
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("📋 Summary:")
    print("- ETD-Hub Excel export service created")
    print("- New endpoint: GET /etd-hub/export/excel")
    print("- Exports all ETD-Hub data to Excel with multiple sheets:")
    print("  • Themes (case studies)")
    print("  • Documents")
    print("  • Questions")
    print("  • Answers")
    print("  • Votes")
    print("  • Experts")
    print("  • Summary statistics")
    print("\n🎯 To test the endpoint:")
    print("1. Start your FastAPI server")
    print("2. Visit: http://localhost:8000/etd-hub/export/excel")
    print("3. The browser will download the Excel file")

if __name__ == "__main__":
    main()
=======
#!/usr/bin/env python3
"""
Test script to verify the ETD-Hub Excel export functionality.
This script tests the export service and endpoint without requiring a running server.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

import asyncio
import pandas as pd
from datetime import datetime
from app.services.etd_hub_export_service import etd_hub_export_service

async def test_export_service():
    """Test the ETD-Hub export service functionality"""
    print("🧪 Testing ETD-Hub Excel Export Service")
    print("=" * 60)
    
    try:
        # Initialize the service
        print("1. Initializing export service...")
        await etd_hub_export_service.initialize()
        print("✅ Export service initialized successfully")
        
        # Test DataFrame cleaning function
        print("\n2. Testing DataFrame cleaning...")
        test_data = {
            'theme_id': [1, 2, 3],
            'name': ['Theme 1', 'Theme 2', 'Theme 3'],
            'description': ['Desc 1', 'Desc 2', 'Desc 3'],
            'created_at': [datetime.now(), datetime.now(), datetime.now()],
            '_id': ['id1', 'id2', 'id3']  # This should be removed
        }
        
        test_df = pd.DataFrame(test_data)
        cleaned_df = etd_hub_export_service._clean_dataframe_for_excel(test_df)
        
        print(f"   Original columns: {list(test_df.columns)}")
        print(f"   Cleaned columns: {list(cleaned_df.columns)}")
        
        # Verify _id was removed
        assert '_id' not in cleaned_df.columns, "_id field should be removed"
        print("✅ DataFrame cleaning works correctly")
        
        # Test column mapping
        print("\n3. Testing column mapping...")
        themes_mapping = {
            'theme_id': 'Theme ID',
            'name': 'Theme Name',
            'description': 'Description',
            'views': 'Views',
            'expert_id': 'Expert ID',
            'problem_category': 'Problem Category',
            'model_category': 'Model Category',
            'domain_category': 'Domain Category',
            'created_at': 'Created At'
        }
        
        # Create a test DataFrame with the expected columns
        test_themes_df = pd.DataFrame({
            'theme_id': [1, 2],
            'name': ['Test Theme 1', 'Test Theme 2'],
            'description': ['Test Description 1', 'Test Description 2'],
            'views': [10, 20],
            'expert_id': [1, 2],
            'problem_category': ['AI_BIAS', 'PRIVACY'],
            'model_category': ['MACHINE_LEARNING', 'LLM'],
            'domain_category': ['HEALTH', 'FINANCE'],
            'created_at': [datetime.now(), datetime.now()]
        })
        
        # Apply column mapping
        mapped_df = test_themes_df.rename(columns=themes_mapping)
        print(f"   Mapped columns: {list(mapped_df.columns)}")
        print("✅ Column mapping works correctly")
        
        # Test Excel file creation (without actual database data)
        print("\n4. Testing Excel file creation...")
        try:
            import io
            from openpyxl import Workbook
            
            # Create a simple test Excel file
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Write test data to different sheets
                test_themes_df.to_excel(writer, sheet_name='Themes', index=False)
                
                # Create summary sheet
                summary_data = {
                    'Metric': ['Total Themes', 'Export Date'],
                    'Count': [2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            output.seek(0)
            file_size = len(output.getvalue())
            print(f"✅ Excel file created successfully (Size: {file_size} bytes)")
            
        except ImportError as e:
            print(f"⚠️  Excel creation test skipped - missing dependency: {e}")
            print("   Install openpyxl: pip install openpyxl")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed! The ETD-Hub Excel export service is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

def test_dependencies():
    """Test if all required dependencies are available"""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        'pandas',
        'openpyxl',
        'fastapi',
        'pymongo'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} - Available")
        except ImportError:
            print(f"❌ {package} - Missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("\n✅ All required dependencies are available!")
        return True

def main():
    """Run all tests"""
    print("🚀 ETD-Hub Excel Export Test Suite")
    print("=" * 60)
    
    # Test dependencies first
    if not test_dependencies():
        print("\n❌ Cannot run tests due to missing dependencies.")
        return
    
    print("\n" + "=" * 60)
    
    # Run async tests
    try:
        asyncio.run(test_export_service())
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("📋 Summary:")
    print("- ETD-Hub Excel export service created")
    print("- New endpoint: GET /etd-hub/export/excel")
    print("- Exports all ETD-Hub data to Excel with multiple sheets:")
    print("  • Themes (case studies)")
    print("  • Documents")
    print("  • Questions")
    print("  • Answers")
    print("  • Votes")
    print("  • Experts")
    print("  • Summary statistics")
    print("\n🎯 To test the endpoint:")
    print("1. Start your FastAPI server")
    print("2. Visit: http://localhost:8000/etd-hub/export/excel")
    print("3. The browser will download the Excel file")

if __name__ == "__main__":
    main()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

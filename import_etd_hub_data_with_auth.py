#!/usr/bin/env python3
"""
Script to import ETD-Hub data from exported_models.json into MongoDB with authentication support
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.etd_hub import (
    Theme, Document, Question, Answer, Vote, Expert,
    ProblemCategory, ModelCategory, DomainCategory, AreaOfExpertise
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ETDHubDataImporter:
    def __init__(self, mongodb_url: str, database_name: str, username: Optional[str] = None, password: Optional[str] = None):
        self.mongodb_url = mongodb_url
        self.database_name = database_name
        self.username = username
        self.password = password
        self.client = None
        self.db = None
        self.themes_collection = None
        self.documents_collection = None
        self.questions_collection = None
        self.answers_collection = None
        self.votes_collection = None
        self.experts_collection = None

    async def initialize(self):
        """Initialize database connections"""
        try:
            # Build MongoDB URL with authentication if credentials are provided
            mongodb_url = self.mongodb_url
            if self.username and self.password:
                # Parse the URL and add authentication
                if "://" in mongodb_url:
                    protocol, rest = mongodb_url.split("://", 1)
                    mongodb_url = f"{protocol}://{self.username}:{self.password}@{rest}"
                else:
                    mongodb_url = f"mongodb://{self.username}:{self.password}@{mongodb_url}"
            
            logger.info(f"Connecting to MongoDB: {mongodb_url.replace(self.password or '', '***') if self.password else mongodb_url}")
            
            self.client = AsyncIOMotorClient(mongodb_url)
            self.db = self.client[self.database_name]
            
            # Test the connection
            await self.client.admin.command('ping')
            logger.info("Connected to MongoDB successfully")
            
            self.themes_collection = self.db.etd_themes
            self.documents_collection = self.db.etd_documents
            self.questions_collection = self.db.etd_questions
            self.answers_collection = self.db.etd_answers
            self.votes_collection = self.db.etd_votes
            self.experts_collection = self.db.etd_experts
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def parse_created_at(self, date_str: str) -> datetime:
        """Parse ISO date string to datetime object"""
        try:
            # Handle both formats: "2025-07-20T08:34:34Z" and "2025-07-21T00:23:20.272Z"
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            return datetime.fromisoformat(date_str)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return datetime.utcnow()

    def map_problem_category(self, category: str) -> ProblemCategory:
        """Map problem category string to enum"""
        category_map = {
            "AI BIAS": ProblemCategory.AI_BIAS,
            "PRIVACY": ProblemCategory.PRIVACY,
            "TRANSPARENCY": ProblemCategory.TRANSPARENCY,
            "ACCOUNTABILITY": ProblemCategory.ACCOUNTABILITY,
            "FAIRNESS": ProblemCategory.FAIRNESS,
        }
        return category_map.get(category, ProblemCategory.OTHER)

    def map_model_category(self, category: str) -> ModelCategory:
        """Map model category string to enum"""
        category_map = {
            "Machine Learning": ModelCategory.MACHINE_LEARNING,
            "Machine Vision": ModelCategory.MACHINE_VISION,
            "LLM": ModelCategory.LLM,
            "NLP": ModelCategory.NLP,
            "Computer Vision": ModelCategory.COMPUTER_VISION,
            "Recommendation": ModelCategory.RECOMMENDATION,
        }
        return category_map.get(category, ModelCategory.OTHER)

    def map_domain_category(self, category: str) -> DomainCategory:
        """Map domain category string to enum"""
        category_map = {
            "Justice": DomainCategory.JUSTICE,
            "Health": DomainCategory.HEALTH,
            "Finance": DomainCategory.FINANCE,
            "Education": DomainCategory.EDUCATION,
            "Social": DomainCategory.SOCIAL,
            "Social Media": DomainCategory.SOCIAL_MEDIA,
            "Transport": DomainCategory.TRANSPORT,
            "Urban Planning": DomainCategory.URBAN_PLANNING,
            "Marketing & Sales": DomainCategory.MARKETING_SALES,
        }
        return category_map.get(category, DomainCategory.OTHER)

    def map_area_of_expertise(self, area: str) -> AreaOfExpertise:
        """Map area of expertise string to enum"""
        area_map = {
            "AI Expert": AreaOfExpertise.AI_EXPERT,
            "AI Ethics Expert": AreaOfExpertise.AI_ETHICS_EXPERT,
            "Research": AreaOfExpertise.RESEARCH,
            "Legal Professional": AreaOfExpertise.LEGAL_PROFESSIONAL,
            "Policy": AreaOfExpertise.POLICY,
            "NGO": AreaOfExpertise.NGO,
            "Enterprise": AreaOfExpertise.ENTERPRISE,
            "Citizen": AreaOfExpertise.CITIZEN,
        }
        return area_map.get(area, AreaOfExpertise.OTHER)

    async def import_themes(self, themes_data: List[Dict[str, Any]]) -> int:
        """Import themes data"""
        logger.info(f"Importing {len(themes_data)} themes...")
        
        imported_count = 0
        for theme_data in themes_data:
            try:
                # Convert string dates to datetime objects
                if 'created_at' in theme_data:
                    theme_data['created_at'] = self.parse_created_at(theme_data['created_at'])
                
                # Map categories to enums
                theme_data['problem_category'] = self.map_problem_category(theme_data.get('problem_category', 'OTHER'))
                theme_data['model_category'] = self.map_model_category(theme_data.get('model_category', 'OTHER'))
                theme_data['domain_category'] = self.map_domain_category(theme_data.get('domain_category', 'OTHER'))
                
                # Create theme object
                theme = Theme(**theme_data)
                
                # Insert into database
                await self.themes_collection.insert_one(theme.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import theme {theme_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} themes")
        return imported_count

    async def import_documents(self, documents_data: List[Dict[str, Any]]) -> int:
        """Import documents data"""
        logger.info(f"Importing {len(documents_data)} documents...")
        
        imported_count = 0
        for document_data in documents_data:
            try:
                # Convert string dates to datetime objects
                if 'created_at' in document_data:
                    document_data['created_at'] = self.parse_created_at(document_data['created_at'])
                
                # Create document object
                document = Document(**document_data)
                
                # Insert into database
                await self.documents_collection.insert_one(document.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import document {document_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} documents")
        return imported_count

    async def import_questions(self, questions_data: List[Dict[str, Any]]) -> int:
        """Import questions data"""
        logger.info(f"Importing {len(questions_data)} questions...")
        
        imported_count = 0
        for question_data in questions_data:
            try:
                # Convert string dates to datetime objects
                if 'created_at' in question_data:
                    question_data['created_at'] = self.parse_created_at(question_data['created_at'])
                
                # Create question object
                question = Question(**question_data)
                
                # Insert into database
                await self.questions_collection.insert_one(question.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import question {question_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} questions")
        return imported_count

    async def import_answers(self, answers_data: List[Dict[str, Any]]) -> int:
        """Import answers data"""
        logger.info(f"Importing {len(answers_data)} answers...")
        
        imported_count = 0
        for answer_data in answers_data:
            try:
                # Convert string dates to datetime objects
                if 'created_at' in answer_data:
                    answer_data['created_at'] = self.parse_created_at(answer_data['created_at'])
                
                # Create answer object
                answer = Answer(**answer_data)
                
                # Insert into database
                await self.answers_collection.insert_one(answer.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import answer {answer_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} answers")
        return imported_count

    async def import_votes(self, votes_data: List[Dict[str, Any]]) -> int:
        """Import votes data"""
        logger.info(f"Importing {len(votes_data)} votes...")
        
        imported_count = 0
        for vote_data in votes_data:
            try:
                # Convert string dates to datetime objects
                if 'created_at' in vote_data:
                    vote_data['created_at'] = self.parse_created_at(vote_data['created_at'])
                if 'updated_at' in vote_data:
                    vote_data['updated_at'] = self.parse_created_at(vote_data['updated_at'])
                
                # Create vote object
                vote = Vote(**vote_data)
                
                # Insert into database
                await self.votes_collection.insert_one(vote.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import vote {vote_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} votes")
        return imported_count

    async def import_experts(self, experts_data: List[Dict[str, Any]]) -> int:
        """Import experts data"""
        logger.info(f"Importing {len(experts_data)} experts...")
        
        imported_count = 0
        for expert_data in experts_data:
            try:
                # Convert string dates to datetime objects
                if 'date_joined' in expert_data:
                    expert_data['date_joined'] = self.parse_created_at(expert_data['date_joined'])
                
                # Map area of expertise to enum
                expert_data['area_of_expertise'] = self.map_area_of_expertise(expert_data.get('area_of_expertise', 'OTHER'))
                
                # Create expert object
                expert = Expert(**expert_data)
                
                # Insert into database
                await self.experts_collection.insert_one(expert.dict(by_alias=True))
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import expert {expert_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Successfully imported {imported_count} experts")
        return imported_count

    async def clear_existing_data(self):
        """Clear existing ETD-Hub data"""
        logger.info("Clearing existing ETD-Hub data...")
        
        await self.themes_collection.delete_many({})
        await self.documents_collection.delete_many({})
        await self.questions_collection.delete_many({})
        await self.answers_collection.delete_many({})
        await self.votes_collection.delete_many({})
        await self.experts_collection.delete_many({})
        
        logger.info("Existing data cleared")

    async def import_data(self, json_file_path: str, clear_existing: bool = True):
        """Import all ETD-Hub data from JSON file"""
        try:
            # Load JSON data
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded data from {json_file_path}")
            
            # Clear existing data if requested
            if clear_existing:
                await self.clear_existing_data()
            
            # Import each entity type
            total_imported = 0
            
            # Import themes
            if 'Theme' in data and data['Theme']:
                imported = await self.import_themes(data['Theme'])
                total_imported += imported
            
            # Import documents
            if 'Document' in data and data['Document']:
                imported = await self.import_documents(data['Document'])
                total_imported += imported
            
            # Import questions
            if 'Question' in data and data['Question']:
                imported = await self.import_questions(data['Question'])
                total_imported += imported
            
            # Import answers
            if 'Answer' in data and data['Answer']:
                imported = await self.import_answers(data['Answer'])
                total_imported += imported
            
            # Import votes
            if 'Vote' in data and data['Vote']:
                imported = await self.import_votes(data['Vote'])
                total_imported += imported
            
            # Import experts
            if 'Expert' in data and data['Expert']:
                imported = await self.import_experts(data['Expert'])
                total_imported += imported
            
            logger.info(f"Import completed! Total records imported: {total_imported}")
            
            # Print summary
            await self.print_import_summary()
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise

    async def print_import_summary(self):
        """Print summary of imported data"""
        try:
            themes_count = await self.themes_collection.count_documents({})
            documents_count = await self.documents_collection.count_documents({})
            questions_count = await self.questions_collection.count_documents({})
            answers_count = await self.answers_collection.count_documents({})
            votes_count = await self.votes_collection.count_documents({})
            experts_count = await self.experts_collection.count_documents({})
            
            logger.info("=== Import Summary ===")
            logger.info(f"Themes: {themes_count}")
            logger.info(f"Documents: {documents_count}")
            logger.info(f"Questions: {questions_count}")
            logger.info(f"Answers: {answers_count}")
            logger.info(f"Votes: {votes_count}")
            logger.info(f"Experts: {experts_count}")
            logger.info("=====================")
            
        except Exception as e:
            logger.error(f"Failed to print import summary: {e}")


async def main():
    """Main function to run the import"""
    
    # MongoDB configuration - UPDATE THESE VALUES
    MONGODB_URL = "mongodb://localhost:27017"  # Update if different
    DATABASE_NAME = "data_warehouse"  # Update if different
    USERNAME = "admin"  # Set to your MongoDB username if authentication is required
    PASSWORD = "password"  # Set to your MongoDB password if authentication is required
    
    # Example with authentication:
    # USERNAME = "your_username"
    # PASSWORD = "your_password"
    
    importer = ETDHubDataImporter(
        mongodb_url=MONGODB_URL,
        database_name=DATABASE_NAME,
        username=USERNAME,
        password=PASSWORD
    )
    
    try:
        await importer.initialize()
        
        # Import data from exported_models.json
        await importer.import_data('exported_models.json', clear_existing=True)
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise
    finally:
        await importer.close()


if __name__ == "__main__":
    asyncio.run(main())

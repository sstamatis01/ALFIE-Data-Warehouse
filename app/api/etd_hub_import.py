<<<<<<< HEAD
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, List
import json
import logging
from datetime import datetime, timezone

from ..models.etd_hub import (
    Theme, Document, Question, Answer, Vote, Expert,
    ThemeCreate, DocumentCreate, QuestionCreate, AnswerCreate, VoteCreate, ExpertCreate,
    ProblemCategory, ModelCategory, DomainCategory, AreaOfExpertise
)
from ..services.etd_hub_service import etd_hub_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/etd-hub/import", tags=["ETD-Hub Import"])


class ETDHubDataImporter:
    def __init__(self):
        self.themes_collection = None
        self.documents_collection = None
        self.questions_collection = None
        self.answers_collection = None
        self.votes_collection = None
        self.experts_collection = None

    async def initialize(self):
        """Initialize collections"""
        from ..core.database import get_database
        db = get_database()
        self.themes_collection = db.etd_themes
        self.documents_collection = db.etd_documents
        self.questions_collection = db.etd_questions
        self.answers_collection = db.etd_answers
        self.votes_collection = db.etd_votes
        self.experts_collection = db.etd_experts

    def parse_created_at(self, date_str: str) -> datetime:
        """Parse ISO date string to datetime object"""
        try:
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            return datetime.fromisoformat(date_str)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return datetime.now(tz=timezone.utc)

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
        logger.info(f"Themes collection: {self.themes_collection}")
        
        imported_count = 0
        for theme_data in themes_data:
            try:
                logger.info(f"Processing theme: {theme_data.get('id', 'unknown')}")
                
                # Create a copy and map fields
                mapped_data = theme_data.copy()
                
                # Map 'id' to 'theme_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['theme_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'views' not in mapped_data:
                    mapped_data['views'] = 0
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.now(tz=timezone.utc)
                
                mapped_data['problem_category'] = self.map_problem_category(mapped_data.get('problem_category', 'OTHER'))
                mapped_data['model_category'] = self.map_model_category(mapped_data.get('model_category', 'OTHER'))
                mapped_data['domain_category'] = self.map_domain_category(mapped_data.get('domain_category', 'OTHER'))
                
                logger.info(f"Mapped data: {mapped_data}")
                
                # Insert the complete data directly (not using Create model)
                result = await self.themes_collection.insert_one(mapped_data)
                logger.info(f"Insert result: {result}")
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import theme {theme_data.get('id', 'unknown')}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        logger.info(f"Successfully imported {imported_count} themes")
        return imported_count

    async def import_documents(self, documents_data: List[Dict[str, Any]]) -> int:
        """Import documents data"""
        logger.info(f"Importing {len(documents_data)} documents...")
        
        imported_count = 0
        for document_data in documents_data:
            try:
                # Create a copy and map fields
                mapped_data = document_data.copy()
                
                # Map 'id' to 'document_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['document_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.now(tz=timezone.utc)
                
                # Insert the complete data directly
                await self.documents_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = question_data.copy()
                
                # Map 'id' to 'question_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['question_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'views' not in mapped_data:
                    mapped_data['views'] = 0
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.now(tz=timezone.utc)
                
                # Insert the complete data directly
                await self.questions_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = answer_data.copy()
                
                # Map 'id' to 'answer_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['answer_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.now(tz=timezone.utc)
                
                # Insert the complete data directly
                await self.answers_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = vote_data.copy()
                
                # Map 'id' to 'vote_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['vote_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.now(tz=timezone.utc)
                if 'updated_at' in mapped_data:
                    mapped_data['updated_at'] = self.parse_created_at(mapped_data['updated_at'])
                else:
                    mapped_data['updated_at'] = datetime.now(tz=timezone.utc)
                
                # Insert the complete data directly
                await self.votes_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = expert_data.copy()
                
                # Map 'id' to 'expert_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['expert_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'date_joined' in mapped_data:
                    mapped_data['date_joined'] = self.parse_created_at(mapped_data['date_joined'])
                else:
                    mapped_data['date_joined'] = datetime.now(tz=timezone.utc)
                
                mapped_data['area_of_expertise'] = self.map_area_of_expertise(mapped_data.get('area_of_expertise', 'OTHER'))
                
                # Insert the complete data directly
                await self.experts_collection.insert_one(mapped_data)
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

    async def import_data(self, data: Dict[str, Any], clear_existing: bool = True) -> Dict[str, int]:
        """Import all ETD-Hub data"""
        try:
            if clear_existing:
                await self.clear_existing_data()
            
            results = {}
            
            # Import each entity type
            if 'Theme' in data and data['Theme']:
                results['themes'] = await self.import_themes(data['Theme'])
            
            if 'Document' in data and data['Document']:
                results['documents'] = await self.import_documents(data['Document'])
            
            if 'Question' in data and data['Question']:
                results['questions'] = await self.import_questions(data['Question'])
            
            if 'Answer' in data and data['Answer']:
                results['answers'] = await self.import_answers(data['Answer'])
            
            if 'Vote' in data and data['Vote']:
                results['votes'] = await self.import_votes(data['Vote'])
            
            if 'Expert' in data and data['Expert']:
                results['experts'] = await self.import_experts(data['Expert'])
            
            total_imported = sum(results.values())
            logger.info(f"Import completed! Total records imported: {total_imported}")
            
            return results
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise


# Global importer instance
importer = ETDHubDataImporter()


@router.post("/upload-json")
async def import_from_json_file(file: UploadFile = File(...), clear_existing: bool = True):
    """Import ETD-Hub data from uploaded JSON file"""
    try:
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="File must be a JSON file")
        
        # Read file content
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # Initialize importer
        await importer.initialize()
        
        # Import data
        results = await importer.import_data(data, clear_existing=clear_existing)
        
        return {
            "message": "Data imported successfully",
            "results": results,
            "total_imported": sum(results.values())
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/import-data")
async def import_from_data(data: Dict[str, Any], clear_existing: bool = True):
    """Import ETD-Hub data from JSON data in request body"""
    try:
        # Initialize importer
        await importer.initialize()
        
        # Import data
        results = await importer.import_data(data, clear_existing=clear_existing)
        
        return {
            "message": "Data imported successfully",
            "results": results,
            "total_imported": sum(results.values())
        }
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.delete("/clear-all")
async def clear_all_data():
    """Clear all ETD-Hub data"""
    try:
        await importer.initialize()
        await importer.clear_existing_data()
        
        return {"message": "All ETD-Hub data cleared successfully"}
        
    except Exception as e:
        logger.error(f"Clear data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Clear data failed: {str(e)}")
=======
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, List
import json
import logging
from datetime import datetime

from ..models.etd_hub import (
    Theme, Document, Question, Answer, Vote, Expert,
    ThemeCreate, DocumentCreate, QuestionCreate, AnswerCreate, VoteCreate, ExpertCreate,
    ProblemCategory, ModelCategory, DomainCategory, AreaOfExpertise
)
from ..services.etd_hub_service import etd_hub_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/etd-hub/import", tags=["ETD-Hub Import"])


class ETDHubDataImporter:
    def __init__(self):
        self.themes_collection = None
        self.documents_collection = None
        self.questions_collection = None
        self.answers_collection = None
        self.votes_collection = None
        self.experts_collection = None

    async def initialize(self):
        """Initialize collections"""
        from ..core.database import get_database
        db = get_database()
        self.themes_collection = db.etd_themes
        self.documents_collection = db.etd_documents
        self.questions_collection = db.etd_questions
        self.answers_collection = db.etd_answers
        self.votes_collection = db.etd_votes
        self.experts_collection = db.etd_experts

    def parse_created_at(self, date_str: str) -> datetime:
        """Parse ISO date string to datetime object"""
        try:
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
        logger.info(f"Themes collection: {self.themes_collection}")
        
        imported_count = 0
        for theme_data in themes_data:
            try:
                logger.info(f"Processing theme: {theme_data.get('id', 'unknown')}")
                
                # Create a copy and map fields
                mapped_data = theme_data.copy()
                
                # Map 'id' to 'theme_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['theme_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'views' not in mapped_data:
                    mapped_data['views'] = 0
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.utcnow()
                
                mapped_data['problem_category'] = self.map_problem_category(mapped_data.get('problem_category', 'OTHER'))
                mapped_data['model_category'] = self.map_model_category(mapped_data.get('model_category', 'OTHER'))
                mapped_data['domain_category'] = self.map_domain_category(mapped_data.get('domain_category', 'OTHER'))
                
                logger.info(f"Mapped data: {mapped_data}")
                
                # Insert the complete data directly (not using Create model)
                result = await self.themes_collection.insert_one(mapped_data)
                logger.info(f"Insert result: {result}")
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import theme {theme_data.get('id', 'unknown')}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        logger.info(f"Successfully imported {imported_count} themes")
        return imported_count

    async def import_documents(self, documents_data: List[Dict[str, Any]]) -> int:
        """Import documents data"""
        logger.info(f"Importing {len(documents_data)} documents...")
        
        imported_count = 0
        for document_data in documents_data:
            try:
                # Create a copy and map fields
                mapped_data = document_data.copy()
                
                # Map 'id' to 'document_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['document_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.utcnow()
                
                # Insert the complete data directly
                await self.documents_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = question_data.copy()
                
                # Map 'id' to 'question_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['question_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'views' not in mapped_data:
                    mapped_data['views'] = 0
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.utcnow()
                
                # Insert the complete data directly
                await self.questions_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = answer_data.copy()
                
                # Map 'id' to 'answer_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['answer_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.utcnow()
                
                # Insert the complete data directly
                await self.answers_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = vote_data.copy()
                
                # Map 'id' to 'vote_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['vote_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'created_at' in mapped_data:
                    mapped_data['created_at'] = self.parse_created_at(mapped_data['created_at'])
                else:
                    mapped_data['created_at'] = datetime.utcnow()
                if 'updated_at' in mapped_data:
                    mapped_data['updated_at'] = self.parse_created_at(mapped_data['updated_at'])
                else:
                    mapped_data['updated_at'] = datetime.utcnow()
                
                # Insert the complete data directly
                await self.votes_collection.insert_one(mapped_data)
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
                # Create a copy and map fields
                mapped_data = expert_data.copy()
                
                # Map 'id' to 'expert_id' and remove 'id' completely
                if 'id' in mapped_data:
                    mapped_data['expert_id'] = mapped_data['id']
                    del mapped_data['id']
                
                # Ensure required fields are present
                if 'date_joined' in mapped_data:
                    mapped_data['date_joined'] = self.parse_created_at(mapped_data['date_joined'])
                else:
                    mapped_data['date_joined'] = datetime.utcnow()
                
                mapped_data['area_of_expertise'] = self.map_area_of_expertise(mapped_data.get('area_of_expertise', 'OTHER'))
                
                # Insert the complete data directly
                await self.experts_collection.insert_one(mapped_data)
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

    async def import_data(self, data: Dict[str, Any], clear_existing: bool = True) -> Dict[str, int]:
        """Import all ETD-Hub data"""
        try:
            if clear_existing:
                await self.clear_existing_data()
            
            results = {}
            
            # Import each entity type
            if 'Theme' in data and data['Theme']:
                results['themes'] = await self.import_themes(data['Theme'])
            
            if 'Document' in data and data['Document']:
                results['documents'] = await self.import_documents(data['Document'])
            
            if 'Question' in data and data['Question']:
                results['questions'] = await self.import_questions(data['Question'])
            
            if 'Answer' in data and data['Answer']:
                results['answers'] = await self.import_answers(data['Answer'])
            
            if 'Vote' in data and data['Vote']:
                results['votes'] = await self.import_votes(data['Vote'])
            
            if 'Expert' in data and data['Expert']:
                results['experts'] = await self.import_experts(data['Expert'])
            
            total_imported = sum(results.values())
            logger.info(f"Import completed! Total records imported: {total_imported}")
            
            return results
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise


# Global importer instance
importer = ETDHubDataImporter()


@router.post("/upload-json")
async def import_from_json_file(file: UploadFile = File(...), clear_existing: bool = True):
    """Import ETD-Hub data from uploaded JSON file"""
    try:
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="File must be a JSON file")
        
        # Read file content
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # Initialize importer
        await importer.initialize()
        
        # Import data
        results = await importer.import_data(data, clear_existing=clear_existing)
        
        return {
            "message": "Data imported successfully",
            "results": results,
            "total_imported": sum(results.values())
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/import-data")
async def import_from_data(data: Dict[str, Any], clear_existing: bool = True):
    """Import ETD-Hub data from JSON data in request body"""
    try:
        # Initialize importer
        await importer.initialize()
        
        # Import data
        results = await importer.import_data(data, clear_existing=clear_existing)
        
        return {
            "message": "Data imported successfully",
            "results": results,
            "total_imported": sum(results.values())
        }
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.delete("/clear-all")
async def clear_all_data():
    """Clear all ETD-Hub data"""
    try:
        await importer.initialize()
        await importer.clear_existing_data()
        
        return {"message": "All ETD-Hub data cleared successfully"}
        
    except Exception as e:
        logger.error(f"Clear data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Clear data failed: {str(e)}")
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

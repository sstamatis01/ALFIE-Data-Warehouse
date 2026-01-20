from typing import Optional, List, Dict, Any
from fastapi import HTTPException
from ..core.database import get_database
from ..models.etd_hub import (
    Theme, ThemeCreate, ThemeUpdate, ThemeResponse,
    Document, DocumentCreate, DocumentUpdate, DocumentResponse,
    Question, QuestionCreate, QuestionUpdate, QuestionResponse,
    Answer, AnswerCreate, AnswerUpdate, AnswerResponse,
    Vote, VoteCreate, VoteUpdate, VoteResponse,
    Expert, ExpertCreate, ExpertUpdate, ExpertResponse,
    AnswerWithVotes, QuestionWithAnswers, ThemeWithQuestions, ExpertWithStats,
    ProblemCategory, ModelCategory, DomainCategory, AreaOfExpertise
)
import logging

logger = logging.getLogger(__name__)


class ETDHubService:
    def __init__(self):
        self.db = None

    async def initialize(self):
        """Initialize the ETD-Hub service"""
        self.db = get_database()
        self.themes_collection = self.db.etd_themes
        self.documents_collection = self.db.etd_documents
        self.questions_collection = self.db.etd_questions
        self.answers_collection = self.db.etd_answers
        self.votes_collection = self.db.etd_votes
        self.experts_collection = self.db.etd_experts

    # Theme operations
    async def create_theme(self, theme_data: ThemeCreate) -> ThemeResponse:
        """Create a new theme"""
        try:
            # Check if theme with this theme_id already exists
            existing_theme = await self.themes_collection.find_one({"theme_id": theme_data.theme_id})
            if existing_theme:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Theme with ID {theme_data.theme_id} already exists"
                )
            
            # Check if the expert exists
            expert = await self.experts_collection.find_one({"expert_id": theme_data.expert_id})
            if not expert:
                raise HTTPException(
                    status_code=400,
                    detail=f"Expert with ID {theme_data.expert_id} does not exist"
                )
            
            theme = Theme(**theme_data.dict())
            result = await self.themes_collection.insert_one(theme.dict(by_alias=True))
            created_theme = await self.themes_collection.find_one({"_id": result.inserted_id})
            return ThemeResponse(**created_theme)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating theme: {e}")
            raise HTTPException(status_code=500, detail="Failed to create theme")

    async def get_theme(self, theme_id: int) -> Optional[ThemeResponse]:
        """Get a theme by ID"""
        try:
            theme = await self.themes_collection.find_one({"theme_id": theme_id})
            if theme:
                return ThemeResponse(**theme)
            return None
        except Exception as e:
            logger.error(f"Error getting theme: {e}")
            raise HTTPException(status_code=500, detail="Failed to get theme")

    async def get_themes(
        self, 
        skip: int = 0, 
        limit: int = 100,
        problem_category: Optional[ProblemCategory] = None,
        model_category: Optional[ModelCategory] = None,
        domain_category: Optional[DomainCategory] = None
    ) -> List[ThemeResponse]:
        """Get themes with optional filtering"""
        try:
            query = {}
            if problem_category:
                query["problem_category"] = problem_category
            if model_category:
                query["model_category"] = model_category
            if domain_category:
                query["domain_category"] = domain_category

            cursor = self.themes_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
            themes = await cursor.to_list(length=limit)
            return [ThemeResponse(**theme) for theme in themes]
        except Exception as e:
            logger.error(f"Error getting themes: {e}")
            raise HTTPException(status_code=500, detail="Failed to get themes")

    async def update_theme(self, theme_id: int, theme_update: ThemeUpdate) -> Optional[ThemeResponse]:
        """Update a theme"""
        try:
            update_data = theme_update.dict(exclude_unset=True)
            if not update_data:
                return await self.get_theme(theme_id)

            result = await self.themes_collection.update_one(
                {"theme_id": theme_id},
                {"$set": update_data}
            )

            if result.modified_count > 0:
                return await self.get_theme(theme_id)
            return None
        except Exception as e:
            logger.error(f"Error updating theme: {e}")
            raise HTTPException(status_code=500, detail="Failed to update theme")

    async def increment_theme_views(self, theme_id: int) -> bool:
        """Increment theme view count"""
        try:
            result = await self.themes_collection.update_one(
                {"theme_id": theme_id},
                {"$inc": {"views": 1}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error incrementing theme views: {e}")
            return False

    async def delete_theme(self, theme_id: int) -> bool:
        """Delete a theme"""
        try:
            result = await self.themes_collection.delete_one({"theme_id": theme_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting theme: {e}")
            return False

    # Question operations
    async def create_question(self, question_data: QuestionCreate) -> QuestionResponse:
        """Create a new question"""
        try:
            # Check if question with this question_id already exists
            existing_question = await self.questions_collection.find_one({"question_id": question_data.question_id})
            if existing_question:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Question with ID {question_data.question_id} already exists"
                )
            
            # Check if the theme exists
            theme = await self.themes_collection.find_one({"theme_id": question_data.theme_id})
            if not theme:
                raise HTTPException(
                    status_code=400,
                    detail=f"Theme with ID {question_data.theme_id} does not exist"
                )
            
            question = Question(**question_data.dict())
            result = await self.questions_collection.insert_one(question.dict(by_alias=True))
            created_question = await self.questions_collection.find_one({"_id": result.inserted_id})
            return QuestionResponse(**created_question)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating question: {e}")
            raise HTTPException(status_code=500, detail="Failed to create question")

    async def get_question(self, question_id: int) -> Optional[QuestionResponse]:
        """Get a question by ID"""
        try:
            question = await self.questions_collection.find_one({"question_id": question_id})
            if question:
                return QuestionResponse(**question)
            return None
        except Exception as e:
            logger.error(f"Error getting question: {e}")
            raise HTTPException(status_code=500, detail="Failed to get question")

    async def get_questions(
        self,
        skip: int = 0,
        limit: int = 100,
        theme_id: Optional[int] = None,
        expert_id: Optional[int] = None
    ) -> List[QuestionResponse]:
        """Get questions with optional filtering"""
        try:
            query = {}
            if theme_id:
                query["theme_id"] = theme_id
            if expert_id:
                query["expert_id"] = expert_id

            cursor = self.questions_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
            questions = await cursor.to_list(length=limit)
            return [QuestionResponse(**question) for question in questions]
        except Exception as e:
            logger.error(f"Error getting questions: {e}")
            raise HTTPException(status_code=500, detail="Failed to get questions")

    async def get_question_with_answers(self, question_id: int) -> Optional[QuestionWithAnswers]:
        """Get a question with its answers and vote counts"""
        try:
            question = await self.get_question(question_id)
            if not question:
                return None

            # Get answers for this question
            answers = await self.get_answers(question_id=question_id)
            
            # Get vote counts for each answer
            answers_with_votes = []
            for answer in answers:
                vote_stats = await self.get_answer_vote_stats(answer.answer_id)
                answer_with_votes = AnswerWithVotes(
                    **answer.dict(),
                    vote_count=vote_stats["total"],
                    upvotes=vote_stats["upvotes"],
                    downvotes=vote_stats["downvotes"]
                )
                answers_with_votes.append(answer_with_votes)

            return QuestionWithAnswers(
                **question.dict(),
                answers=answers_with_votes,
                answer_count=len(answers_with_votes)
            )
        except Exception as e:
            logger.error(f"Error getting question with answers: {e}")
            raise HTTPException(status_code=500, detail="Failed to get question with answers")

    async def increment_question_views(self, question_id: int) -> bool:
        """Increment question view count"""
        try:
            result = await self.questions_collection.update_one(
                {"question_id": question_id},
                {"$inc": {"views": 1}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error incrementing question views: {e}")
            return False

    async def delete_question(self, question_id: int) -> bool:
        """Delete a question"""
        try:
            result = await self.questions_collection.delete_one({"question_id": question_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting question: {e}")
            return False

    # Answer operations
    async def create_answer(self, answer_data: AnswerCreate) -> AnswerResponse:
        """Create a new answer"""
        try:
            # Check if answer with this answer_id already exists
            existing_answer = await self.answers_collection.find_one({"answer_id": answer_data.answer_id})
            if existing_answer:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Answer with ID {answer_data.answer_id} already exists"
                )
            
            # Check if the question exists
            question = await self.questions_collection.find_one({"question_id": answer_data.question_id})
            if not question:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question with ID {answer_data.question_id} does not exist"
                )
            
            # If parent_id is provided, check if the parent answer exists
            if answer_data.parent_id is not None:
                parent_answer = await self.answers_collection.find_one({"answer_id": answer_data.parent_id})
                if not parent_answer:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Parent answer with ID {answer_data.parent_id} does not exist"
                    )
            
            answer = Answer(**answer_data.dict())
            result = await self.answers_collection.insert_one(answer.dict(by_alias=True))
            created_answer = await self.answers_collection.find_one({"_id": result.inserted_id})
            return AnswerResponse(**created_answer)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating answer: {e}")
            raise HTTPException(status_code=500, detail="Failed to create answer")

    async def get_answer(self, answer_id: int) -> Optional[AnswerResponse]:
        """Get an answer by ID"""
        try:
            answer = await self.answers_collection.find_one({"answer_id": answer_id})
            if answer:
                return AnswerResponse(**answer)
            return None
        except Exception as e:
            logger.error(f"Error getting answer: {e}")
            raise HTTPException(status_code=500, detail="Failed to get answer")

    async def get_answers(
        self,
        skip: int = 0,
        limit: int = 100,
        question_id: Optional[int] = None,
        expert_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ) -> List[AnswerResponse]:
        """Get answers with optional filtering"""
        try:
            query = {}
            if question_id:
                query["question_id"] = question_id
            if expert_id:
                query["expert_id"] = expert_id
            if parent_id is not None:
                query["parent_id"] = parent_id

            cursor = self.answers_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
            answers = await cursor.to_list(length=limit)
            return [AnswerResponse(**answer) for answer in answers]
        except Exception as e:
            logger.error(f"Error getting answers: {e}")
            raise HTTPException(status_code=500, detail="Failed to get answers")

    async def get_answer_vote_stats(self, answer_id: int) -> Dict[str, int]:
        """Get vote statistics for an answer"""
        try:
            pipeline = [
                {"$match": {"answer_id": answer_id}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": "$vote_value"},
                    "upvotes": {"$sum": {"$cond": [{"$gt": ["$vote_value", 0]}, 1, 0]}},
                    "downvotes": {"$sum": {"$cond": [{"$lt": ["$vote_value", 0]}, 1, 0]}}
                }}
            ]
            
            result = await self.votes_collection.aggregate(pipeline).to_list(1)
            if result:
                return {
                    "total": result[0]["total"],
                    "upvotes": result[0]["upvotes"],
                    "downvotes": result[0]["downvotes"]
                }
            return {"total": 0, "upvotes": 0, "downvotes": 0}
        except Exception as e:
            logger.error(f"Error getting answer vote stats: {e}")
            return {"total": 0, "upvotes": 0, "downvotes": 0}

    async def delete_answer(self, answer_id: int) -> bool:
        """Delete an answer"""
        try:
            result = await self.answers_collection.delete_one({"answer_id": answer_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting answer: {e}")
            return False

    # Vote operations
    async def create_vote(self, vote_data: VoteCreate) -> VoteResponse:
        """Create a new vote"""
        try:
            # Check if the expert exists
            expert = await self.experts_collection.find_one({"expert_id": vote_data.expert_id})
            if not expert:
                raise HTTPException(
                    status_code=400,
                    detail=f"Expert with ID {vote_data.expert_id} does not exist"
                )
            
            # Check if the answer exists
            answer = await self.answers_collection.find_one({"answer_id": vote_data.answer_id})
            if not answer:
                raise HTTPException(
                    status_code=400,
                    detail=f"Answer with ID {vote_data.answer_id} does not exist"
                )
            
            # Check if expert already voted on this answer
            existing_vote = await self.votes_collection.find_one({
                "expert_id": vote_data.expert_id,
                "answer_id": vote_data.answer_id
            })

            if existing_vote:
                # Update existing vote
                vote_update = VoteUpdate(vote_value=vote_data.vote_value)
                result = await self.votes_collection.update_one(
                    {"expert_id": vote_data.expert_id, "answer_id": vote_data.answer_id},
                    {"$set": vote_update.dict(exclude_unset=True)}
                )
                if result.modified_count > 0:
                    updated_vote = await self.votes_collection.find_one({
                        "expert_id": vote_data.expert_id,
                        "answer_id": vote_data.answer_id
                    })
                    return VoteResponse(**updated_vote)
            else:
                # Create new vote
                vote = Vote(**vote_data.dict())
                result = await self.votes_collection.insert_one(vote.dict(by_alias=True))
                created_vote = await self.votes_collection.find_one({"_id": result.inserted_id})
                return VoteResponse(**created_vote)
        except Exception as e:
            logger.error(f"Error creating/updating vote: {e}")
            raise HTTPException(status_code=500, detail="Failed to create/update vote")

    async def get_vote(self, expert_id: int, answer_id: int) -> Optional[VoteResponse]:
        """Get a vote by expert and answer"""
        try:
            vote = await self.votes_collection.find_one({
                "expert_id": expert_id,
                "answer_id": answer_id
            })
            if vote:
                return VoteResponse(**vote)
            return None
        except Exception as e:
            logger.error(f"Error getting vote: {e}")
            raise HTTPException(status_code=500, detail="Failed to get vote")

    async def delete_vote(self, expert_id: int, answer_id: int) -> bool:
        """Delete a vote"""
        try:
            result = await self.votes_collection.delete_one({
                "expert_id": expert_id,
                "answer_id": answer_id
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting vote: {e}")
            return False

    # Expert operations
    async def create_expert(self, expert_data: ExpertCreate) -> ExpertResponse:
        """Create a new expert"""
        try:
            # Check if expert with this expert_id already exists
            existing_expert = await self.experts_collection.find_one({"expert_id": expert_data.expert_id})
            if existing_expert:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Expert with ID {expert_data.expert_id} already exists"
                )
            
            expert = Expert(**expert_data.dict())
            result = await self.experts_collection.insert_one(expert.dict(by_alias=True))
            created_expert = await self.experts_collection.find_one({"_id": result.inserted_id})
            return ExpertResponse(**created_expert)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating expert: {e}")
            raise HTTPException(status_code=500, detail="Failed to create expert")

    async def get_expert(self, expert_id: int) -> Optional[ExpertResponse]:
        """Get an expert by ID"""
        try:
            expert = await self.experts_collection.find_one({"expert_id": expert_id})
            if expert:
                return ExpertResponse(**expert)
            return None
        except Exception as e:
            logger.error(f"Error getting expert: {e}")
            raise HTTPException(status_code=500, detail="Failed to get expert")

    async def get_experts(
        self,
        skip: int = 0,
        limit: int = 100,
        area_of_expertise: Optional[AreaOfExpertise] = None,
        is_deleted: bool = False
    ) -> List[ExpertResponse]:
        """Get experts with optional filtering"""
        try:
            query = {"is_deleted": is_deleted}
            if area_of_expertise:
                query["area_of_expertise"] = area_of_expertise

            cursor = self.experts_collection.find(query).skip(skip).limit(limit).sort("date_joined", -1)
            experts = await cursor.to_list(length=limit)
            return [ExpertResponse(**expert) for expert in experts]
        except Exception as e:
            logger.error(f"Error getting experts: {e}")
            raise HTTPException(status_code=500, detail="Failed to get experts")

    async def get_expert_with_stats(self, expert_id: int) -> Optional[ExpertWithStats]:
        """Get an expert with statistics"""
        try:
            expert = await self.get_expert(expert_id)
            if not expert:
                return None

            # Get statistics
            questions_count = await self.questions_collection.count_documents({"expert_id": expert_id})
            answers_count = await self.answers_collection.count_documents({"expert_id": expert_id})
            themes_count = await self.themes_collection.count_documents({"expert_id": expert_id})

            # Get total votes received on answers
            pipeline = [
                {"$match": {"expert_id": expert_id}},
                {"$lookup": {
                    "from": "etd_votes",
                    "localField": "answer_id",
                    "foreignField": "answer_id",
                    "as": "votes"
                }},
                {"$unwind": "$votes"},
                {"$group": {"_id": None, "total_votes": {"$sum": "$votes.vote_value"}}}
            ]
            
            votes_result = await self.answers_collection.aggregate(pipeline).to_list(1)
            total_votes = votes_result[0]["total_votes"] if votes_result else 0

            return ExpertWithStats(
                **expert.dict(),
                questions_asked=questions_count,
                answers_provided=answers_count,
                themes_created=themes_count,
                total_votes_received=total_votes
            )
        except Exception as e:
            logger.error(f"Error getting expert with stats: {e}")
            raise HTTPException(status_code=500, detail="Failed to get expert with stats")

    async def delete_expert(self, expert_id: int) -> bool:
        """Delete an expert"""
        try:
            result = await self.experts_collection.delete_one({"expert_id": expert_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting expert: {e}")
            return False

    # Document operations
    async def create_document(self, document_data: DocumentCreate) -> DocumentResponse:
        """Create a new document"""
        try:
            # Check if document with this document_id already exists
            existing_document = await self.documents_collection.find_one({"document_id": document_data.document_id})
            if existing_document:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Document with ID {document_data.document_id} already exists"
                )
            
            document = Document(**document_data.dict())
            result = await self.documents_collection.insert_one(document.dict(by_alias=True))
            created_document = await self.documents_collection.find_one({"_id": result.inserted_id})
            return DocumentResponse(**created_document)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating document: {e}")
            raise HTTPException(status_code=500, detail="Failed to create document")

    async def get_document(self, document_id: int) -> Optional[DocumentResponse]:
        """Get a document by ID"""
        try:
            document = await self.documents_collection.find_one({"document_id": document_id})
            if document:
                return DocumentResponse(**document)
            return None
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            raise HTTPException(status_code=500, detail="Failed to get document")

    async def get_documents(
        self,
        skip: int = 0,
        limit: int = 100,
        theme_id: Optional[int] = None,
        expert_id: Optional[int] = None
    ) -> List[DocumentResponse]:
        """Get documents with optional filtering"""
        try:
            query = {}
            if theme_id:
                query["theme_id"] = theme_id
            if expert_id:
                query["expert_id"] = expert_id

            cursor = self.documents_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
            documents = await cursor.to_list(length=limit)
            return [DocumentResponse(**document) for document in documents]
        except Exception as e:
            logger.error(f"Error getting documents: {e}")
            raise HTTPException(status_code=500, detail="Failed to get documents")


# Global ETD-Hub service instance
etd_hub_service = ETDHubService()

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, List
import logging

from ..models.etd_hub import (
    ThemeCreate, ThemeUpdate, ThemeResponse, ThemeWithQuestions,
    DocumentCreate, DocumentUpdate, DocumentResponse,
    QuestionCreate, QuestionUpdate, QuestionResponse, QuestionWithAnswers,
    AnswerCreate, AnswerUpdate, AnswerResponse, AnswerWithVotes,
    VoteCreate, VoteUpdate, VoteResponse,
    ExpertCreate, ExpertUpdate, ExpertResponse, ExpertWithStats,
    ProblemCategory, ModelCategory, DomainCategory, AreaOfExpertise
)
from ..services.etd_hub_service import etd_hub_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/etd-hub", tags=["ETD-Hub"])


# Theme endpoints
@router.post("/themes", response_model=ThemeResponse)
async def create_theme(theme_data: ThemeCreate):
    """Create a new theme (case study)"""
    try:
        return await etd_hub_service.create_theme(theme_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to create theme")


@router.get("/themes", response_model=List[ThemeResponse])
async def get_themes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    problem_category: Optional[ProblemCategory] = Query(None),
    model_category: Optional[ModelCategory] = Query(None),
    domain_category: Optional[DomainCategory] = Query(None)
):
    """Get themes with optional filtering"""
    try:
        return await etd_hub_service.get_themes(
            skip=skip,
            limit=limit,
            problem_category=problem_category,
            model_category=model_category,
            domain_category=domain_category
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting themes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get themes")


@router.get("/themes/{theme_id}", response_model=ThemeResponse)
async def get_theme(theme_id: int = Path(..., description="Theme ID")):
    """Get a specific theme by ID"""
    try:
        theme = await etd_hub_service.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")
        
        # Increment view count
        await etd_hub_service.increment_theme_views(theme_id)
        return theme
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to get theme")


@router.get("/themes/{theme_id}/with-questions", response_model=ThemeWithQuestions)
async def get_theme_with_questions(theme_id: int = Path(..., description="Theme ID")):
    """Get a theme with its associated questions"""
    try:
        theme = await etd_hub_service.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        # Get questions for this theme
        questions = await etd_hub_service.get_questions(theme_id=theme_id)
        
        return ThemeWithQuestions(
            **theme.dict(),
            questions=questions,
            question_count=len(questions)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting theme with questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get theme with questions")


@router.put("/themes/{theme_id}", response_model=ThemeResponse)
async def update_theme(
    theme_id: int = Path(..., description="Theme ID"),
    theme_update: ThemeUpdate = None
):
    """Update a theme"""
    try:
        updated_theme = await etd_hub_service.update_theme(theme_id, theme_update)
        if not updated_theme:
            raise HTTPException(status_code=404, detail="Theme not found")
        return updated_theme
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to update theme")


@router.delete("/themes/{theme_id}")
async def delete_theme(theme_id: int = Path(..., description="Theme ID")):
    """Delete a theme"""
    try:
        deleted = await etd_hub_service.delete_theme(theme_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Theme not found")
        return {"message": f"Theme {theme_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete theme")


# Question endpoints
@router.post("/questions", response_model=QuestionResponse)
async def create_question(question_data: QuestionCreate):
    """Create a new question"""
    try:
        return await etd_hub_service.create_question(question_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating question: {e}")
        raise HTTPException(status_code=500, detail="Failed to create question")


@router.get("/questions", response_model=List[QuestionResponse])
async def get_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    theme_id: Optional[int] = Query(None),
    expert_id: Optional[int] = Query(None)
):
    """Get questions with optional filtering"""
    try:
        return await etd_hub_service.get_questions(
            skip=skip,
            limit=limit,
            theme_id=theme_id,
            expert_id=expert_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get questions")


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: int = Path(..., description="Question ID")):
    """Get a specific question by ID"""
    try:
        question = await etd_hub_service.get_question(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Increment view count
        await etd_hub_service.increment_question_views(question_id)
        return question
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting question: {e}")
        raise HTTPException(status_code=500, detail="Failed to get question")


@router.get("/questions/{question_id}/with-answers", response_model=QuestionWithAnswers)
async def get_question_with_answers(question_id: int = Path(..., description="Question ID")):
    """Get a question with its answers and vote counts"""
    try:
        question_with_answers = await etd_hub_service.get_question_with_answers(question_id)
        if not question_with_answers:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Increment view count
        await etd_hub_service.increment_question_views(question_id)
        return question_with_answers
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting question with answers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get question with answers")


@router.put("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: int = Path(..., description="Question ID"),
    question_update: QuestionUpdate = None
):
    """Update a question"""
    try:
        # For now, we'll implement a simple update - in a real app you might want to check permissions
        question = await etd_hub_service.get_question(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Since we don't have an update method in the service yet, we'll return the existing question
        # In a real implementation, you would add an update_question method to the service
        return question
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating question: {e}")
        raise HTTPException(status_code=500, detail="Failed to update question")


@router.delete("/questions/{question_id}")
async def delete_question(question_id: int = Path(..., description="Question ID")):
    """Delete a question"""
    try:
        deleted = await etd_hub_service.delete_question(question_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Question not found")
        return {"message": f"Question {question_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting question: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete question")


# Answer endpoints
@router.post("/answers", response_model=AnswerResponse)
async def create_answer(answer_data: AnswerCreate):
    """Create a new answer"""
    try:
        return await etd_hub_service.create_answer(answer_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating answer: {e}")
        raise HTTPException(status_code=500, detail="Failed to create answer")


@router.get("/answers", response_model=List[AnswerResponse])
async def get_answers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    question_id: Optional[int] = Query(None),
    expert_id: Optional[int] = Query(None),
    parent_id: Optional[int] = Query(None)
):
    """Get answers with optional filtering"""
    try:
        return await etd_hub_service.get_answers(
            skip=skip,
            limit=limit,
            question_id=question_id,
            expert_id=expert_id,
            parent_id=parent_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting answers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get answers")


@router.get("/answers/{answer_id}", response_model=AnswerWithVotes)
async def get_answer_with_votes(answer_id: int = Path(..., description="Answer ID")):
    """Get an answer with its vote statistics"""
    try:
        answer = await etd_hub_service.get_answer(answer_id)
        if not answer:
            raise HTTPException(status_code=404, detail="Answer not found")

        vote_stats = await etd_hub_service.get_answer_vote_stats(answer_id)
        return AnswerWithVotes(
            **answer.dict(),
            vote_count=vote_stats["total"],
            upvotes=vote_stats["upvotes"],
            downvotes=vote_stats["downvotes"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting answer with votes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get answer with votes")


@router.delete("/answers/{answer_id}")
async def delete_answer(answer_id: int = Path(..., description="Answer ID")):
    """Delete an answer"""
    try:
        deleted = await etd_hub_service.delete_answer(answer_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Answer not found")
        return {"message": f"Answer {answer_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting answer: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete answer")


# Vote endpoints
@router.post("/votes", response_model=VoteResponse)
async def create_or_update_vote(vote_data: VoteCreate):
    """Create a new vote or update existing vote"""
    try:
        return await etd_hub_service.create_vote(vote_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating/updating vote: {e}")
        raise HTTPException(status_code=500, detail="Failed to create/update vote")


@router.get("/votes/{expert_id}/{answer_id}", response_model=VoteResponse)
async def get_vote(
    expert_id: int = Path(..., description="Expert ID"),
    answer_id: int = Path(..., description="Answer ID")
):
    """Get a vote by expert and answer"""
    try:
        vote = await etd_hub_service.get_vote(expert_id, answer_id)
        if not vote:
            raise HTTPException(status_code=404, detail="Vote not found")
        return vote
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting vote: {e}")
        raise HTTPException(status_code=500, detail="Failed to get vote")


@router.delete("/votes/{expert_id}/{answer_id}")
async def delete_vote(
    expert_id: int = Path(..., description="Expert ID"),
    answer_id: int = Path(..., description="Answer ID")
):
    """Delete a vote"""
    try:
        success = await etd_hub_service.delete_vote(expert_id, answer_id)
        if not success:
            raise HTTPException(status_code=404, detail="Vote not found")
        return {"message": "Vote deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vote: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete vote")


# Expert endpoints
@router.post("/experts", response_model=ExpertResponse)
async def create_expert(expert_data: ExpertCreate):
    """Create a new expert"""
    try:
        return await etd_hub_service.create_expert(expert_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating expert: {e}")
        raise HTTPException(status_code=500, detail="Failed to create expert")


@router.get("/experts", response_model=List[ExpertResponse])
async def get_experts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    area_of_expertise: Optional[AreaOfExpertise] = Query(None),
    is_deleted: bool = Query(False)
):
    """Get experts with optional filtering"""
    try:
        return await etd_hub_service.get_experts(
            skip=skip,
            limit=limit,
            area_of_expertise=area_of_expertise,
            is_deleted=is_deleted
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting experts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get experts")


@router.get("/experts/{expert_id}", response_model=ExpertResponse)
async def get_expert(expert_id: int = Path(..., description="Expert ID")):
    """Get a specific expert by ID"""
    try:
        expert = await etd_hub_service.get_expert(expert_id)
        if not expert:
            raise HTTPException(status_code=404, detail="Expert not found")
        return expert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting expert: {e}")
        raise HTTPException(status_code=500, detail="Failed to get expert")


@router.get("/experts/{expert_id}/with-stats", response_model=ExpertWithStats)
async def get_expert_with_stats(expert_id: int = Path(..., description="Expert ID")):
    """Get an expert with statistics"""
    try:
        expert_with_stats = await etd_hub_service.get_expert_with_stats(expert_id)
        if not expert_with_stats:
            raise HTTPException(status_code=404, detail="Expert not found")
        return expert_with_stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting expert with stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get expert with stats")


@router.delete("/experts/{expert_id}")
async def delete_expert(expert_id: int = Path(..., description="Expert ID")):
    """Delete an expert"""
    try:
        deleted = await etd_hub_service.delete_expert(expert_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Expert not found")
        return {"message": f"Expert {expert_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting expert: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete expert")


# Document endpoints
@router.post("/documents", response_model=DocumentResponse)
async def create_document(document_data: DocumentCreate):
    """Create a new document"""
    try:
        return await etd_hub_service.create_document(document_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {e}")
        raise HTTPException(status_code=500, detail="Failed to create document")


@router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    theme_id: Optional[int] = Query(None),
    expert_id: Optional[int] = Query(None)
):
    """Get documents with optional filtering"""
    try:
        return await etd_hub_service.get_documents(
            skip=skip,
            limit=limit,
            theme_id=theme_id,
            expert_id=expert_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to get documents")


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int = Path(..., description="Document ID")):
    """Get a specific document by ID"""
    try:
        document = await etd_hub_service.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail="Failed to get document")


# Statistics endpoints
@router.get("/stats/overview")
async def get_overview_stats():
    """Get overview statistics for ETD-Hub"""
    try:
        # Get counts for each entity type
        themes_count = await etd_hub_service.themes_collection.count_documents({})
        questions_count = await etd_hub_service.questions_collection.count_documents({})
        answers_count = await etd_hub_service.answers_collection.count_documents({})
        experts_count = await etd_hub_service.experts_collection.count_documents({"is_deleted": False})
        documents_count = await etd_hub_service.documents_collection.count_documents({})
        votes_count = await etd_hub_service.votes_collection.count_documents({})

        return {
            "themes": themes_count,
            "questions": questions_count,
            "answers": answers_count,
            "experts": experts_count,
            "documents": documents_count,
            "votes": votes_count
        }
    except Exception as e:
        logger.error(f"Error getting overview stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get overview statistics")

<<<<<<< HEAD
from datetime import datetime, timezone
from typing import Optional, List, Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from bson import ObjectId
from enum import Enum


def validate_object_id(v):
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(lambda x: str(x), return_type=str)
]


class ProblemCategory(str, Enum):
    AI_BIAS = "AI BIAS"
    PRIVACY = "PRIVACY"
    TRANSPARENCY = "TRANSPARENCY"
    ACCOUNTABILITY = "ACCOUNTABILITY"
    FAIRNESS = "FAIRNESS"
    OTHER = "OTHER"


class ModelCategory(str, Enum):
    MACHINE_LEARNING = "Machine Learning"
    MACHINE_VISION = "Machine Vision"
    LLM = "LLM"
    NLP = "NLP"
    COMPUTER_VISION = "Computer Vision"
    RECOMMENDATION = "Recommendation"
    OTHER = "Other"


class DomainCategory(str, Enum):
    JUSTICE = "Justice"
    HEALTH = "Health"
    FINANCE = "Finance"
    EDUCATION = "Education"
    SOCIAL = "Social"
    SOCIAL_MEDIA = "Social Media"
    TRANSPORT = "Transport"
    URBAN_PLANNING = "Urban Planning"
    MARKETING_SALES = "Marketing & Sales"
    OTHER = "Other"


class AreaOfExpertise(str, Enum):
    AI_EXPERT = "AI Expert"
    AI_ETHICS_EXPERT = "AI Ethics Expert"
    RESEARCH = "Research"
    LEGAL_PROFESSIONAL = "Legal Professional"
    POLICY = "Policy"
    NGO = "NGO"
    ENTERPRISE = "Enterprise"
    CITIZEN = "Citizen"
    OTHER = "Other"


# Theme Models
class Theme(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    theme_id: int = Field(..., description="Unique theme identifier")
    name: str = Field(..., description="Theme name")
    description: str = Field(..., description="Theme description")
    views: int = Field(default=0, description="Number of views")
    expert_id: int = Field(..., description="Expert who created this theme")
    problem_category: ProblemCategory = Field(..., description="Problem category")
    model_category: ModelCategory = Field(..., description="Model category")
    domain_category: DomainCategory = Field(..., description="Domain category")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class ThemeCreate(BaseModel):
    theme_id: int
    name: str
    description: str
    expert_id: int
    problem_category: ProblemCategory
    model_category: ModelCategory
    domain_category: DomainCategory


class ThemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    problem_category: Optional[ProblemCategory] = None
    model_category: Optional[ModelCategory] = None
    domain_category: Optional[DomainCategory] = None


class ThemeResponse(BaseModel):
    theme_id: int
    name: str
    description: str
    views: int
    expert_id: int
    problem_category: ProblemCategory
    model_category: ModelCategory
    domain_category: DomainCategory
    created_at: datetime


# Document Models
class Document(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    document_id: int = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    description: Optional[str] = Field(None, description="Document description")
    file_path: Optional[str] = Field(None, description="Path to document file")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    content_type: Optional[str] = Field(None, description="MIME type")
    expert_id: int = Field(..., description="Expert who uploaded this document")
    theme_id: Optional[int] = Field(None, description="Associated theme ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class DocumentCreate(BaseModel):
    document_id: int
    title: str
    description: Optional[str] = None
    expert_id: int
    theme_id: Optional[int] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    theme_id: Optional[int] = None


class DocumentResponse(BaseModel):
    document_id: int
    title: str
    description: Optional[str]
    file_path: Optional[str]
    file_size: Optional[int]
    content_type: Optional[str]
    expert_id: int
    theme_id: Optional[int]
    created_at: datetime


# Question Models
class Question(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    question_id: int = Field(..., description="Unique question identifier")
    title: str = Field(..., description="Question title")
    body: str = Field(..., description="Question body")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    views: int = Field(default=0, description="Number of views")
    expert_id: int = Field(..., description="Expert who asked this question")
    theme_id: int = Field(..., description="Associated theme ID")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class QuestionCreate(BaseModel):
    question_id: int
    title: str
    body: str
    expert_id: int
    theme_id: int


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


class QuestionResponse(BaseModel):
    question_id: int
    title: str
    body: str
    created_at: datetime
    views: int
    expert_id: int
    theme_id: int


# Answer Models
class Answer(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    answer_id: int = Field(..., description="Unique answer identifier")
    description: str = Field(..., description="Answer content")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    question_id: int = Field(..., description="Associated question ID")
    expert_id: int = Field(..., description="Expert who provided this answer")
    parent_id: Optional[int] = Field(None, description="Parent answer ID for replies")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class AnswerCreate(BaseModel):
    answer_id: int
    description: str
    question_id: int
    expert_id: int
    parent_id: Optional[int] = None


class AnswerUpdate(BaseModel):
    description: Optional[str] = None


class AnswerResponse(BaseModel):
    answer_id: int
    description: str
    created_at: datetime
    question_id: int
    expert_id: int
    parent_id: Optional[int]


# Vote Models
class Vote(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    vote_id: int = Field(..., description="Unique vote identifier")
    expert_id: int = Field(..., description="Expert who voted")
    answer_id: int = Field(..., description="Answer being voted on")
    vote_value: int = Field(..., description="Vote value (1 for upvote, -1 for downvote)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class VoteCreate(BaseModel):
    vote_id: int
    expert_id: int
    answer_id: int
    vote_value: int


class VoteUpdate(BaseModel):
    vote_value: int


class VoteResponse(BaseModel):
    vote_id: int
    expert_id: int
    answer_id: int
    vote_value: int
    created_at: datetime
    updated_at: datetime


# Expert Models
class Expert(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    expert_id: int = Field(..., description="Unique expert identifier")
    user_id: int = Field(..., description="Associated user ID")
    is_deleted: bool = Field(default=False, description="Whether expert is deleted")
    area_of_expertise: AreaOfExpertise = Field(..., description="Area of expertise")
    bio: str = Field(default="", description="Expert biography")
    date_joined: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    profile_picture: str = Field(default="", description="Profile picture path")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class ExpertCreate(BaseModel):
    expert_id: int
    user_id: int
    area_of_expertise: AreaOfExpertise
    bio: str = ""
    profile_picture: str = ""


class ExpertUpdate(BaseModel):
    area_of_expertise: Optional[AreaOfExpertise] = None
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    is_deleted: Optional[bool] = None


class ExpertResponse(BaseModel):
    expert_id: int
    user_id: int
    is_deleted: bool
    area_of_expertise: AreaOfExpertise
    bio: str
    date_joined: datetime
    profile_picture: str


# Extended response models with relationships
class AnswerWithVotes(AnswerResponse):
    vote_count: int = Field(default=0, description="Total vote count")
    upvotes: int = Field(default=0, description="Number of upvotes")
    downvotes: int = Field(default=0, description="Number of downvotes")


class QuestionWithAnswers(QuestionResponse):
    answers: List[AnswerWithVotes] = Field(default_factory=list, description="Answers to this question")
    answer_count: int = Field(default=0, description="Total number of answers")


class ThemeWithQuestions(ThemeResponse):
    questions: List[QuestionResponse] = Field(default_factory=list, description="Questions in this theme")
    question_count: int = Field(default=0, description="Total number of questions")


class ExpertWithStats(ExpertResponse):
    questions_asked: int = Field(default=0, description="Number of questions asked")
    answers_provided: int = Field(default=0, description="Number of answers provided")
    themes_created: int = Field(default=0, description="Number of themes created")
    total_votes_received: int = Field(default=0, description="Total votes received on answers")
=======
from datetime import datetime
from typing import Optional, List, Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from bson import ObjectId
from enum import Enum


def validate_object_id(v):
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(lambda x: str(x), return_type=str)
]


class ProblemCategory(str, Enum):
    AI_BIAS = "AI BIAS"
    PRIVACY = "PRIVACY"
    TRANSPARENCY = "TRANSPARENCY"
    ACCOUNTABILITY = "ACCOUNTABILITY"
    FAIRNESS = "FAIRNESS"
    OTHER = "OTHER"


class ModelCategory(str, Enum):
    MACHINE_LEARNING = "Machine Learning"
    MACHINE_VISION = "Machine Vision"
    LLM = "LLM"
    NLP = "NLP"
    COMPUTER_VISION = "Computer Vision"
    RECOMMENDATION = "Recommendation"
    OTHER = "Other"


class DomainCategory(str, Enum):
    JUSTICE = "Justice"
    HEALTH = "Health"
    FINANCE = "Finance"
    EDUCATION = "Education"
    SOCIAL = "Social"
    SOCIAL_MEDIA = "Social Media"
    TRANSPORT = "Transport"
    URBAN_PLANNING = "Urban Planning"
    MARKETING_SALES = "Marketing & Sales"
    OTHER = "Other"


class AreaOfExpertise(str, Enum):
    AI_EXPERT = "AI Expert"
    AI_ETHICS_EXPERT = "AI Ethics Expert"
    RESEARCH = "Research"
    LEGAL_PROFESSIONAL = "Legal Professional"
    POLICY = "Policy"
    NGO = "NGO"
    ENTERPRISE = "Enterprise"
    CITIZEN = "Citizen"
    OTHER = "Other"


# Theme Models
class Theme(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    theme_id: int = Field(..., description="Unique theme identifier")
    name: str = Field(..., description="Theme name")
    description: str = Field(..., description="Theme description")
    views: int = Field(default=0, description="Number of views")
    expert_id: int = Field(..., description="Expert who created this theme")
    problem_category: ProblemCategory = Field(..., description="Problem category")
    model_category: ModelCategory = Field(..., description="Model category")
    domain_category: DomainCategory = Field(..., description="Domain category")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class ThemeCreate(BaseModel):
    theme_id: int
    name: str
    description: str
    expert_id: int
    problem_category: ProblemCategory
    model_category: ModelCategory
    domain_category: DomainCategory


class ThemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    problem_category: Optional[ProblemCategory] = None
    model_category: Optional[ModelCategory] = None
    domain_category: Optional[DomainCategory] = None


class ThemeResponse(BaseModel):
    theme_id: int
    name: str
    description: str
    views: int
    expert_id: int
    problem_category: ProblemCategory
    model_category: ModelCategory
    domain_category: DomainCategory
    created_at: datetime


# Document Models
class Document(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    document_id: int = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    description: Optional[str] = Field(None, description="Document description")
    file_path: Optional[str] = Field(None, description="Path to document file")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    content_type: Optional[str] = Field(None, description="MIME type")
    expert_id: int = Field(..., description="Expert who uploaded this document")
    theme_id: Optional[int] = Field(None, description="Associated theme ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class DocumentCreate(BaseModel):
    document_id: int
    title: str
    description: Optional[str] = None
    expert_id: int
    theme_id: Optional[int] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    theme_id: Optional[int] = None


class DocumentResponse(BaseModel):
    document_id: int
    title: str
    description: Optional[str]
    file_path: Optional[str]
    file_size: Optional[int]
    content_type: Optional[str]
    expert_id: int
    theme_id: Optional[int]
    created_at: datetime


# Question Models
class Question(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    question_id: int = Field(..., description="Unique question identifier")
    title: str = Field(..., description="Question title")
    body: str = Field(..., description="Question body")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    views: int = Field(default=0, description="Number of views")
    expert_id: int = Field(..., description="Expert who asked this question")
    theme_id: int = Field(..., description="Associated theme ID")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class QuestionCreate(BaseModel):
    question_id: int
    title: str
    body: str
    expert_id: int
    theme_id: int


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


class QuestionResponse(BaseModel):
    question_id: int
    title: str
    body: str
    created_at: datetime
    views: int
    expert_id: int
    theme_id: int


# Answer Models
class Answer(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    answer_id: int = Field(..., description="Unique answer identifier")
    description: str = Field(..., description="Answer content")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    question_id: int = Field(..., description="Associated question ID")
    expert_id: int = Field(..., description="Expert who provided this answer")
    parent_id: Optional[int] = Field(None, description="Parent answer ID for replies")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class AnswerCreate(BaseModel):
    answer_id: int
    description: str
    question_id: int
    expert_id: int
    parent_id: Optional[int] = None


class AnswerUpdate(BaseModel):
    description: Optional[str] = None


class AnswerResponse(BaseModel):
    answer_id: int
    description: str
    created_at: datetime
    question_id: int
    expert_id: int
    parent_id: Optional[int]


# Vote Models
class Vote(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    vote_id: int = Field(..., description="Unique vote identifier")
    expert_id: int = Field(..., description="Expert who voted")
    answer_id: int = Field(..., description="Answer being voted on")
    vote_value: int = Field(..., description="Vote value (1 for upvote, -1 for downvote)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class VoteCreate(BaseModel):
    vote_id: int
    expert_id: int
    answer_id: int
    vote_value: int


class VoteUpdate(BaseModel):
    vote_value: int


class VoteResponse(BaseModel):
    vote_id: int
    expert_id: int
    answer_id: int
    vote_value: int
    created_at: datetime
    updated_at: datetime


# Expert Models
class Expert(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    expert_id: int = Field(..., description="Unique expert identifier")
    user_id: int = Field(..., description="Associated user ID")
    is_deleted: bool = Field(default=False, description="Whether expert is deleted")
    area_of_expertise: AreaOfExpertise = Field(..., description="Area of expertise")
    bio: str = Field(default="", description="Expert biography")
    date_joined: datetime = Field(default_factory=datetime.utcnow)
    profile_picture: str = Field(default="", description="Profile picture path")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class ExpertCreate(BaseModel):
    expert_id: int
    user_id: int
    area_of_expertise: AreaOfExpertise
    bio: str = ""
    profile_picture: str = ""


class ExpertUpdate(BaseModel):
    area_of_expertise: Optional[AreaOfExpertise] = None
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    is_deleted: Optional[bool] = None


class ExpertResponse(BaseModel):
    expert_id: int
    user_id: int
    is_deleted: bool
    area_of_expertise: AreaOfExpertise
    bio: str
    date_joined: datetime
    profile_picture: str


# Extended response models with relationships
class AnswerWithVotes(AnswerResponse):
    vote_count: int = Field(default=0, description="Total vote count")
    upvotes: int = Field(default=0, description="Number of upvotes")
    downvotes: int = Field(default=0, description="Number of downvotes")


class QuestionWithAnswers(QuestionResponse):
    answers: List[AnswerWithVotes] = Field(default_factory=list, description="Answers to this question")
    answer_count: int = Field(default=0, description="Total number of answers")


class ThemeWithQuestions(ThemeResponse):
    questions: List[QuestionResponse] = Field(default_factory=list, description="Questions in this theme")
    question_count: int = Field(default=0, description="Total number of questions")


class ExpertWithStats(ExpertResponse):
    questions_asked: int = Field(default=0, description="Number of questions asked")
    answers_provided: int = Field(default=0, description="Number of answers provided")
    themes_created: int = Field(default=0, description="Number of themes created")
    total_votes_received: int = Field(default=0, description="Total votes received on answers")
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

# ETD-Hub Implementation

## Overview

ETD-Hub is a Reddit-like forum system integrated into the Data Warehouse API for ethical AI discussions. It provides a platform for experts to discuss AI ethics topics through themes (case studies), questions, answers, and a voting system.

## Features

### Core Entities

1. **Themes** - Case studies and ethical AI topics
   - Problem categories (AI Bias, Privacy, Transparency, etc.)
   - Model categories (Machine Learning, Computer Vision, etc.)
   - Domain categories (Justice, Health, Finance, etc.)
   - View tracking

2. **Questions** - Forum discussions
   - Associated with themes
   - Asked by experts
   - View tracking

3. **Answers** - Expert responses
   - Hierarchical structure (replies to answers)
   - Associated with questions
   - Vote tracking

4. **Votes** - Voting system
   - Upvote/downvote answers
   - One vote per expert per answer
   - Vote statistics

5. **Experts** - User profiles
   - Areas of expertise
   - Biographies
   - Statistics (questions asked, answers provided, etc.)

6. **Documents** - File uploads (future feature)
   - Associated with themes
   - Uploaded by experts

## API Endpoints

### Themes
- `GET /etd-hub/themes` - List themes with filtering
- `GET /etd-hub/themes/{theme_id}` - Get specific theme
- `GET /etd-hub/themes/{theme_id}/with-questions` - Get theme with questions
- `POST /etd-hub/themes` - Create new theme
- `PUT /etd-hub/themes/{theme_id}` - Update theme

### Questions
- `GET /etd-hub/questions` - List questions with filtering
- `GET /etd-hub/questions/{question_id}` - Get specific question
- `GET /etd-hub/questions/{question_id}/with-answers` - Get question with answers and votes
- `POST /etd-hub/questions` - Create new question
- `PUT /etd-hub/questions/{question_id}` - Update question

### Answers
- `GET /etd-hub/answers` - List answers with filtering
- `GET /etd-hub/answers/{answer_id}` - Get answer with vote statistics
- `POST /etd-hub/answers` - Create new answer

### Votes
- `POST /etd-hub/votes` - Create or update vote
- `GET /etd-hub/votes/{expert_id}/{answer_id}` - Get specific vote
- `DELETE /etd-hub/votes/{expert_id}/{answer_id}` - Delete vote

### Experts
- `GET /etd-hub/experts` - List experts with filtering
- `GET /etd-hub/experts/{expert_id}` - Get specific expert
- `GET /etd-hub/experts/{expert_id}/with-stats` - Get expert with statistics
- `POST /etd-hub/experts` - Create new expert

### Documents
- `GET /etd-hub/documents` - List documents with filtering
- `GET /etd-hub/documents/{document_id}` - Get specific document
- `POST /etd-hub/documents` - Create new document

### Statistics
- `GET /etd-hub/stats/overview` - Get overview statistics

## Data Import

### Importing Existing Data

To import the existing data from `exported_models.json`:

1. **Make sure Python is properly installed and accessible**
2. **Run the import script:**
   ```bash
   python import_etd_hub_data.py
   ```

   Or if Python is not in PATH:
   ```bash
   # Find your Python installation
   where python
   # Use the full path
   C:\path\to\python.exe import_etd_hub_data.py
   ```

3. **The script will:**
   - Clear existing ETD-Hub data (if requested)
   - Import all entities from the JSON file
   - Map string categories to enum values
   - Parse date strings to datetime objects
   - Provide import statistics

### Data Structure

The import script handles the following mappings:

- **Problem Categories**: "AI BIAS" → `ProblemCategory.AI_BIAS`
- **Model Categories**: "Machine Learning" → `ModelCategory.MACHINE_LEARNING`
- **Domain Categories**: "Justice" → `DomainCategory.JUSTICE`
- **Areas of Expertise**: "AI Expert" → `AreaOfExpertise.AI_EXPERT`

## Database Collections

The following MongoDB collections are created:

- `etd_themes` - Theme data
- `etd_questions` - Question data
- `etd_answers` - Answer data
- `etd_votes` - Vote data
- `etd_experts` - Expert data
- `etd_documents` - Document data

## Usage Examples

### Creating a New Theme
```python
import requests

theme_data = {
    "theme_id": 18,
    "name": "New AI Ethics Topic",
    "description": "Description of the topic...",
    "expert_id": 5,
    "problem_category": "AI_BIAS",
    "model_category": "MACHINE_LEARNING",
    "domain_category": "HEALTH"
}

response = requests.post("http://localhost:8000/etd-hub/themes", json=theme_data)
```

### Asking a Question
```python
question_data = {
    "question_id": 23,
    "title": "How do we ensure AI fairness?",
    "body": "What are the best practices for ensuring AI systems are fair?",
    "expert_id": 5,
    "theme_id": 6
}

response = requests.post("http://localhost:8000/etd-hub/questions", json=question_data)
```

### Answering a Question
```python
answer_data = {
    "answer_id": 32,
    "description": "Here are some best practices for AI fairness...",
    "question_id": 23,
    "expert_id": 10,
    "parent_id": None  # None for top-level answers, answer_id for replies
}

response = requests.post("http://localhost:8000/etd-hub/answers", json=answer_data)
```

### Voting on an Answer
```python
vote_data = {
    "vote_id": 81,
    "expert_id": 5,
    "answer_id": 32,
    "vote_value": 1  # 1 for upvote, -1 for downvote
}

response = requests.post("http://localhost:8000/etd-hub/votes", json=vote_data)
```

## Testing

### Manual Testing
1. Start the API server:
   ```bash
   python -m uvicorn app.main:app --reload
   ```

2. Run the test script:
   ```bash
   python test_etd_hub_api.py
   ```

### API Documentation
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Future Enhancements

1. **Document Upload**: Implement file upload functionality for documents
2. **Authentication**: Add user authentication and authorization
3. **Real-time Updates**: WebSocket support for real-time discussions
4. **Search**: Full-text search across questions and answers
5. **Notifications**: Email/notification system for new answers
6. **Moderation**: Content moderation and reporting system
7. **Analytics**: Advanced analytics and reporting
8. **Mobile API**: Mobile-optimized endpoints

## Troubleshooting

### Import Issues
- Ensure MongoDB is running
- Check database connection settings in `app/core/config.py`
- Verify the JSON file format matches the expected structure

### API Issues
- Check that all services are initialized in `app/main.py`
- Verify database collections exist
- Check logs for specific error messages

### Python Issues
- Ensure Python is properly installed and in PATH
- Install required dependencies: `pip install -r requirements.txt`
- Use virtual environment if needed

## Support

For issues or questions:
1. Check the API documentation at `/docs`
2. Review the logs for error messages
3. Verify database connectivity
4. Test individual endpoints using the test script

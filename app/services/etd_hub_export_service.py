from typing import List, Dict, Any
from datetime import datetime
import io
import logging
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
from ..core.database import get_database

logger = logging.getLogger(__name__)


class ETDHubExportService:
    def __init__(self):
        self.db = None

    async def initialize(self):
        """Initialize the ETD-Hub export service"""
        self.db = get_database()
        self.themes_collection = self.db.etd_themes
        self.documents_collection = self.db.etd_documents
        self.questions_collection = self.db.etd_questions
        self.answers_collection = self.db.etd_answers
        self.votes_collection = self.db.etd_votes
        self.experts_collection = self.db.etd_experts

    async def export_all_data_to_excel(self) -> StreamingResponse:
        """Export all ETD-Hub data to an Excel file with multiple sheets"""
        try:
            # Create Excel writer in memory
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Export each collection to a separate sheet
                await self._export_themes_sheet(writer)
                await self._export_documents_sheet(writer)
                await self._export_questions_sheet(writer)
                await self._export_answers_sheet(writer)
                await self._export_votes_sheet(writer)
                await self._export_experts_sheet(writer)
                await self._export_summary_sheet(writer)
            
            # Reset buffer position
            output.seek(0)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"etd_hub_export_{timestamp}.xlsx"
            
            # Return streaming response
            return StreamingResponse(
                io.BytesIO(output.read()),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        except Exception as e:
            logger.error(f"Error exporting ETD-Hub data to Excel: {e}")
            raise HTTPException(status_code=500, detail="Failed to export ETD-Hub data")

    async def _export_themes_sheet(self, writer: pd.ExcelWriter):
        """Export themes data to Excel sheet"""
        try:
            themes_cursor = self.themes_collection.find({})
            themes_data = await themes_cursor.to_list(length=None)
            
            if themes_data:
                # Convert to DataFrame
                themes_df = pd.DataFrame(themes_data)
                
                # Clean up the data for Excel
                themes_df = self._clean_dataframe_for_excel(themes_df)
                
                # Rename columns for better readability
                column_mapping = {
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
                themes_df = themes_df.rename(columns=column_mapping)
                
                # Write to Excel
                themes_df.to_excel(writer, sheet_name='Themes', index=False)
            else:
                # Create empty sheet with headers
                empty_df = pd.DataFrame(columns=[
                    'Theme ID', 'Theme Name', 'Description', 'Views', 'Expert ID',
                    'Problem Category', 'Model Category', 'Domain Category', 'Created At'
                ])
                empty_df.to_excel(writer, sheet_name='Themes', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting themes: {e}")
            # Create empty sheet on error
            empty_df = pd.DataFrame(columns=['Theme ID', 'Theme Name', 'Description', 'Views', 'Expert ID',
                                           'Problem Category', 'Model Category', 'Domain Category', 'Created At'])
            empty_df.to_excel(writer, sheet_name='Themes', index=False)

    async def _export_documents_sheet(self, writer: pd.ExcelWriter):
        """Export documents data to Excel sheet"""
        try:
            documents_cursor = self.documents_collection.find({})
            documents_data = await documents_cursor.to_list(length=None)
            
            if documents_data:
                documents_df = pd.DataFrame(documents_data)
                documents_df = self._clean_dataframe_for_excel(documents_df)
                
                column_mapping = {
                    'document_id': 'Document ID',
                    'title': 'Title',
                    'description': 'Description',
                    'file_path': 'File Path',
                    'file_size': 'File Size (bytes)',
                    'content_type': 'Content Type',
                    'expert_id': 'Expert ID',
                    'theme_id': 'Theme ID',
                    'created_at': 'Created At'
                }
                documents_df = documents_df.rename(columns=column_mapping)
                
                documents_df.to_excel(writer, sheet_name='Documents', index=False)
            else:
                empty_df = pd.DataFrame(columns=[
                    'Document ID', 'Title', 'Description', 'File Path', 'File Size (bytes)',
                    'Content Type', 'Expert ID', 'Theme ID', 'Created At'
                ])
                empty_df.to_excel(writer, sheet_name='Documents', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting documents: {e}")
            empty_df = pd.DataFrame(columns=['Document ID', 'Title', 'Description', 'File Path', 'File Size (bytes)',
                                           'Content Type', 'Expert ID', 'Theme ID', 'Created At'])
            empty_df.to_excel(writer, sheet_name='Documents', index=False)

    async def _export_questions_sheet(self, writer: pd.ExcelWriter):
        """Export questions data to Excel sheet"""
        try:
            questions_cursor = self.questions_collection.find({})
            questions_data = await questions_cursor.to_list(length=None)
            
            if questions_data:
                questions_df = pd.DataFrame(questions_data)
                questions_df = self._clean_dataframe_for_excel(questions_df)
                
                column_mapping = {
                    'question_id': 'Question ID',
                    'title': 'Question Title',
                    'body': 'Question Body',
                    'created_at': 'Created At',
                    'views': 'Views',
                    'expert_id': 'Expert ID',
                    'theme_id': 'Theme ID'
                }
                questions_df = questions_df.rename(columns=column_mapping)
                
                questions_df.to_excel(writer, sheet_name='Questions', index=False)
            else:
                empty_df = pd.DataFrame(columns=[
                    'Question ID', 'Question Title', 'Question Body', 'Created At',
                    'Views', 'Expert ID', 'Theme ID'
                ])
                empty_df.to_excel(writer, sheet_name='Questions', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting questions: {e}")
            empty_df = pd.DataFrame(columns=['Question ID', 'Question Title', 'Question Body', 'Created At',
                                           'Views', 'Expert ID', 'Theme ID'])
            empty_df.to_excel(writer, sheet_name='Questions', index=False)

    async def _export_answers_sheet(self, writer: pd.ExcelWriter):
        """Export answers data to Excel sheet"""
        try:
            answers_cursor = self.answers_collection.find({})
            answers_data = await answers_cursor.to_list(length=None)
            
            if answers_data:
                answers_df = pd.DataFrame(answers_data)
                answers_df = self._clean_dataframe_for_excel(answers_df)
                
                column_mapping = {
                    'answer_id': 'Answer ID',
                    'description': 'Answer Description',
                    'created_at': 'Created At',
                    'question_id': 'Question ID',
                    'expert_id': 'Expert ID',
                    'parent_id': 'Parent Answer ID'
                }
                answers_df = answers_df.rename(columns=column_mapping)
                
                answers_df.to_excel(writer, sheet_name='Answers', index=False)
            else:
                empty_df = pd.DataFrame(columns=[
                    'Answer ID', 'Answer Description', 'Created At',
                    'Question ID', 'Expert ID', 'Parent Answer ID'
                ])
                empty_df.to_excel(writer, sheet_name='Answers', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting answers: {e}")
            empty_df = pd.DataFrame(columns=['Answer ID', 'Answer Description', 'Created At',
                                           'Question ID', 'Expert ID', 'Parent Answer ID'])
            empty_df.to_excel(writer, sheet_name='Answers', index=False)

    async def _export_votes_sheet(self, writer: pd.ExcelWriter):
        """Export votes data to Excel sheet"""
        try:
            votes_cursor = self.votes_collection.find({})
            votes_data = await votes_cursor.to_list(length=None)
            
            if votes_data:
                votes_df = pd.DataFrame(votes_data)
                votes_df = self._clean_dataframe_for_excel(votes_df)
                
                column_mapping = {
                    'vote_id': 'Vote ID',
                    'expert_id': 'Expert ID',
                    'answer_id': 'Answer ID',
                    'vote_value': 'Vote Value',
                    'created_at': 'Created At',
                    'updated_at': 'Updated At'
                }
                votes_df = votes_df.rename(columns=column_mapping)
                
                # Add vote type column for better readability
                votes_df['Vote Type'] = votes_df['Vote Value'].map({1: 'Upvote', -1: 'Downvote'})
                
                votes_df.to_excel(writer, sheet_name='Votes', index=False)
            else:
                empty_df = pd.DataFrame(columns=[
                    'Vote ID', 'Expert ID', 'Answer ID', 'Vote Value', 'Vote Type',
                    'Created At', 'Updated At'
                ])
                empty_df.to_excel(writer, sheet_name='Votes', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting votes: {e}")
            empty_df = pd.DataFrame(columns=['Vote ID', 'Expert ID', 'Answer ID', 'Vote Value', 'Vote Type',
                                           'Created At', 'Updated At'])
            empty_df.to_excel(writer, sheet_name='Votes', index=False)

    async def _export_experts_sheet(self, writer: pd.ExcelWriter):
        """Export experts data to Excel sheet"""
        try:
            experts_cursor = self.experts_collection.find({})
            experts_data = await experts_cursor.to_list(length=None)
            
            if experts_data:
                experts_df = pd.DataFrame(experts_data)
                experts_df = self._clean_dataframe_for_excel(experts_df)
                
                column_mapping = {
                    'expert_id': 'Expert ID',
                    'user_id': 'User ID',
                    'is_deleted': 'Is Deleted',
                    'area_of_expertise': 'Area of Expertise',
                    'bio': 'Biography',
                    'date_joined': 'Date Joined',
                    'profile_picture': 'Profile Picture'
                }
                experts_df = experts_df.rename(columns=column_mapping)
                
                experts_df.to_excel(writer, sheet_name='Experts', index=False)
            else:
                empty_df = pd.DataFrame(columns=[
                    'Expert ID', 'User ID', 'Is Deleted', 'Area of Expertise',
                    'Biography', 'Date Joined', 'Profile Picture'
                ])
                empty_df.to_excel(writer, sheet_name='Experts', index=False)
                
        except Exception as e:
            logger.error(f"Error exporting experts: {e}")
            empty_df = pd.DataFrame(columns=['Expert ID', 'User ID', 'Is Deleted', 'Area of Expertise',
                                           'Biography', 'Date Joined', 'Profile Picture'])
            empty_df.to_excel(writer, sheet_name='Experts', index=False)

    async def _export_summary_sheet(self, writer: pd.ExcelWriter):
        """Export summary statistics to Excel sheet"""
        try:
            # Get counts for each collection
            themes_count = await self.themes_collection.count_documents({})
            documents_count = await self.documents_collection.count_documents({})
            questions_count = await self.questions_collection.count_documents({})
            answers_count = await self.answers_collection.count_documents({})
            votes_count = await self.votes_collection.count_documents({})
            experts_count = await self.experts_collection.count_documents({})
            
            # Calculate additional statistics
            active_experts_count = await self.experts_collection.count_documents({"is_deleted": False})
            upvotes_count = await self.votes_collection.count_documents({"vote_value": 1})
            downvotes_count = await self.votes_collection.count_documents({"vote_value": -1})
            
            # Create summary data
            summary_data = {
                'Metric': [
                    'Total Themes',
                    'Total Documents',
                    'Total Questions',
                    'Total Answers',
                    'Total Votes',
                    'Total Experts',
                    'Active Experts',
                    'Upvotes',
                    'Downvotes',
                    'Export Date'
                ],
                'Count': [
                    themes_count,
                    documents_count,
                    questions_count,
                    answers_count,
                    votes_count,
                    experts_count,
                    active_experts_count,
                    upvotes_count,
                    downvotes_count,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
        except Exception as e:
            logger.error(f"Error creating summary sheet: {e}")
            # Create basic summary on error
            summary_data = {
                'Metric': ['Export Date'],
                'Count': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

    def _clean_dataframe_for_excel(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean DataFrame for Excel export"""
        # Remove MongoDB _id field if present
        if '_id' in df.columns:
            df = df.drop('_id', axis=1)
        
        # Convert datetime objects to strings for Excel compatibility
        for col in df.columns:
            if df[col].dtype == 'object':
                # Check if column contains datetime objects
                if not df[col].empty and hasattr(df[col].iloc[0], 'strftime'):
                    df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Replace NaN values with empty strings
        df = df.fillna('')
        
        return df


# Create service instance
etd_hub_export_service = ETDHubExportService()

import json
import logging
<<<<<<< HEAD
from datetime import datetime, timezone
=======
from datetime import datetime
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
from typing import Dict, Any, Optional
from aiokafka import AIOKafkaProducer
from ..core.config import settings
from ..models.dataset import DatasetMetadata

logger = logging.getLogger(__name__)


class KafkaProducerService:
    def __init__(self) -> None:
        self.producer: Optional[AIOKafkaProducer] = None
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.client_id = settings.kafka_client_id

    async def start(self) -> None:
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
                key_serializer=lambda x: x.encode('utf-8') if x else None,
            )
            await self.producer.start()
            logger.info(f"Kafka producer started, servers={self.bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise

    async def stop(self) -> None:
        if self.producer:
            try:
                await self.producer.stop()
                logger.info("Kafka producer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")

    async def send_dataset_event(
        self,
        event_type: str,
        dataset_metadata: DatasetMetadata,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping event")
            return

        try:
            payload: Dict[str, Any] = {
                "event_type": event_type,
<<<<<<< HEAD
                "event_id": f"{event_type}_{dataset_metadata.dataset_id}_{int(datetime.now(tz=timezone.utc).timestamp())}",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
=======
                "event_id": f"{event_type}_{dataset_metadata.dataset_id}_{int(datetime.utcnow().timestamp())}",
                "timestamp": datetime.utcnow().isoformat(),
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
                "dataset": {
                    "dataset_id": dataset_metadata.dataset_id,
                    "user_id": dataset_metadata.user_id,
                    "name": dataset_metadata.name,
                    "description": dataset_metadata.description,
                    "version": dataset_metadata.version,
                    "file_type": dataset_metadata.file_type,
                    "file_size": dataset_metadata.file_size,
                    "file_path": dataset_metadata.file_path,
                    "original_filename": dataset_metadata.original_filename,
                    "is_folder": dataset_metadata.is_folder,
                    "file_count": len(dataset_metadata.files) if dataset_metadata.files else 1,
                    "columns": dataset_metadata.columns,
                    "row_count": dataset_metadata.row_count,
                    "data_types": dataset_metadata.data_types,
                    "tags": dataset_metadata.tags,
                    "custom_metadata": dataset_metadata.custom_metadata,
                    "created_at": dataset_metadata.created_at.isoformat(),
                    "updated_at": dataset_metadata.updated_at.isoformat(),
                    "file_hash": dataset_metadata.file_hash,
                },
            }
            if additional_data:
                payload.update(additional_data)

            key = dataset_metadata.dataset_id
            await self.producer.send_and_wait(settings.kafka_dataset_topic, value=payload, key=key)
            logger.info(f"Kafka event sent: {event_type} dataset_id={key}")
        except Exception as e:
            logger.warning(f"Failed to send Kafka event: {e}")

    async def send_dataset_uploaded_event(self, dataset_metadata: DatasetMetadata) -> None:
        await self.send_dataset_event("dataset.uploaded", dataset_metadata)

    async def send_dataset_upload_started_event(
        self,
        *,
        session_id: str,
        conversation_id: str,
        user_id: str,
        dataset_id: str,
        filename: str,
        file_size: int
    ) -> None:
        """Send dataset upload started event for tracking"""
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping dataset upload started event")
            return
        
        payload = {
            "event_type": "dataset.upload.started",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "file_size": file_size,
<<<<<<< HEAD
            "timestamp": datetime.now(tz=timezone.utc).isoformat()
=======
            "timestamp": datetime.utcnow().isoformat()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        try:
            await self.producer.send_and_wait(settings.kafka_dataset_topic, value=payload, key=dataset_id)
            logger.info(f"Dataset upload started event sent for dataset_id={dataset_id}")
        except Exception as e:
            logger.warning(f"Failed to send dataset upload started event: {e}")

    async def send_dataset_upload_completed_event(
        self,
        *,
        session_id: str,
        conversation_id: str,
        user_id: str,
        dataset_id: str,
        filename: str,
        file_size: int,
        record_count: Optional[int] = None,
        columns: Optional[list] = None
    ) -> None:
        """Send dataset upload completed event for tracking"""
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping dataset upload completed event")
            return
        
        payload = {
            "event_type": "dataset.upload.completed",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "file_size": file_size,
            "record_count": record_count,
            "columns": columns,
<<<<<<< HEAD
            "timestamp": datetime.now(tz=timezone.utc).isoformat()
=======
            "timestamp": datetime.utcnow().isoformat()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        try:
            await self.producer.send_and_wait(settings.kafka_dataset_topic, value=payload, key=dataset_id)
            logger.info(f"Dataset upload completed event sent for dataset_id={dataset_id}")
        except Exception as e:
            logger.warning(f"Failed to send dataset upload completed event: {e}")

    async def send_dataset_upload_failed_event(
        self,
        *,
        session_id: str,
        conversation_id: str,
        user_id: str,
        dataset_id: str,
        filename: str,
        error_message: str
    ) -> None:
        """Send dataset upload failed event for tracking"""
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping dataset upload failed event")
            return
        
        payload = {
            "event_type": "dataset.upload.failed",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "error_message": error_message,
<<<<<<< HEAD
            "timestamp": datetime.now(tz=timezone.utc).isoformat()
=======
            "timestamp": datetime.utcnow().isoformat()
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        try:
            await self.producer.send_and_wait(settings.kafka_dataset_topic, value=payload, key=dataset_id)
            logger.info(f"Dataset upload failed event sent for dataset_id={dataset_id}")
        except Exception as e:
            logger.warning(f"Failed to send dataset upload failed event: {e}")

    async def send_dataset_updated_event(self, dataset_metadata: DatasetMetadata) -> None:
        await self.send_dataset_event("dataset.updated", dataset_metadata)

    async def send_dataset_deleted_event(self, dataset_metadata: DatasetMetadata) -> None:
        await self.send_dataset_event("dataset.deleted", dataset_metadata)

    async def send_bias_complete_event(
        self,
        *,
        task_id: str,
        dataset_id: str,
        dataset_version: str,
        user_id: str,
        bias_report_id: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Send bias detection completion event"""
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping bias completion event")
            return
        
        payload = {
            "task_id": task_id,
            "event_type": "bias-detection-complete",
<<<<<<< HEAD
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
=======
            "timestamp": datetime.utcnow().isoformat(),
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        if success:
            payload["output"] = {
                "bias_report_id": bias_report_id,
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "user_id": user_id
            }
            payload["failure"] = None
        else:
            payload["output"] = None
            payload["failure"] = {
                "error_type": "BiasDetectionError",
                "error_message": error_message or "Bias detection failed"
            }
        
        try:
            await self.producer.send_and_wait(settings.kafka_bias_topic, value=payload, key=task_id)
            logger.info(f"Bias completion event sent for task_id={task_id}")
        except Exception as e:
            logger.warning(f"Failed to send bias completion event: {e}")

    async def send_automl_complete_event(
        self,
        *,
        task_id: str,
        user_id: str,
        model_id: str,
        model_version: str,
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Send AutoML completion event"""
        if not self.producer:
<<<<<<< HEAD
            logger.error("❌ Kafka producer not initialized; skipping AutoML completion event")
            logger.error("   This usually means the Kafka producer failed to start during application initialization")
            return
        
        logger.info(f"Preparing AutoML completion event for task_id={task_id}")
        
        payload = {
            "task_id": task_id,
            "event_type": "automl-complete",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
=======
            logger.warning("Kafka producer not initialized; skipping AutoML completion event")
            return
        
        payload = {
            "task_id": task_id,
            "event_type": "automl-complete",
            "timestamp": datetime.utcnow().isoformat(),
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        if success:
            payload["output"] = {
                "model_id": model_id,
                "model_version": model_version,
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "user_id": user_id
            }
            payload["failure"] = None
        else:
            payload["output"] = None
            payload["failure"] = {
                "error_type": "AutoMLError",
                "error_message": error_message or "AutoML training failed"
            }
        
        try:
<<<<<<< HEAD
            logger.info(f"Sending AutoML completion event to topic: {settings.kafka_automl_topic}")
            logger.info(f"Payload: {json.dumps(payload, indent=2, default=str)}")
            await self.producer.send_and_wait(settings.kafka_automl_topic, value=payload, key=task_id)
            logger.info(f"✅ AutoML completion event sent successfully to Kafka for task_id={task_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send AutoML completion event to Kafka: {e}", exc_info=True)
            logger.error(f"   Topic: {settings.kafka_automl_topic}")
            logger.error(f"   Task ID: {task_id}")
            logger.error(f"   Bootstrap servers: {self.bootstrap_servers}")
=======
            await self.producer.send_and_wait(settings.kafka_automl_topic, value=payload, key=task_id)
            logger.info(f"AutoML completion event sent for task_id={task_id}")
        except Exception as e:
            logger.warning(f"Failed to send AutoML completion event: {e}")
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96

    async def send_xai_complete_event(
        self,
        *,
        task_id: str,
        user_id: str,
        dataset_id: str,
        dataset_version: str,
        model_id: str,
        model_version: str,
        xai_report_id: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Send XAI completion event"""
        if not self.producer:
            logger.warning("Kafka producer not initialized; skipping XAI completion event")
            return
        
        payload = {
            "task_id": task_id,
            "event_type": "xai-complete",
<<<<<<< HEAD
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
=======
            "timestamp": datetime.utcnow().isoformat(),
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
        }
        
        if success:
            payload["output"] = {
                "xai_report_id": xai_report_id,
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "user_id": user_id,
                "model_id": model_id,
                "model_version": model_version
            }
            payload["failure"] = None
        else:
            payload["output"] = None
            payload["failure"] = {
                "error_type": "XAIError",
                "error_message": error_message or "XAI report generation failed"
            }
        
        try:
            await self.producer.send_and_wait(settings.kafka_xai_topic, value=payload, key=task_id)
            logger.info(f"XAI completion event sent for task_id={task_id}")
        except Exception as e:
            logger.warning(f"Failed to send XAI completion event: {e}")


kafka_producer_service = KafkaProducerService()


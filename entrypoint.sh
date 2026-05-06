#!/bin/bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
python kafka_agentic_core_consumer_example.py&
python kafka_bias_detector_consumer_example.py&
python kafka_automl_consumer_example.py&
python kafka_xai_consumer_example.py&

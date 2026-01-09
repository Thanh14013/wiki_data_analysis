"""
Ingestion module for Wiki Data Pipeline
Collects data from Wikimedia API and sends to Kafka
"""
from .producer import WikiProducer

__all__ = ['WikiProducer']

"""
Wikimedia Stream Producer
Connects to Wikimedia EventStream API and publishes events to Kafka
"""
import json
import logging
from typing import Optional, Dict, Any
import requests
from kafka import KafkaProducer
from kafka.errors import KafkaError

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WikiProducer:
    """
    Producer for Wikimedia Recent Changes Stream
    Fetches real-time Wikipedia edits and publishes to Kafka
    """
    
    def __init__(self):
        """Initialize producer with settings"""
        self.settings = get_settings()
        self.producer: Optional[KafkaProducer] = None
        self.stats = {
            'sent': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def _create_producer(self) -> KafkaProducer:
        """Create and configure Kafka producer"""
        try:
            producer = KafkaProducer(
                bootstrap_servers=self.settings.kafka.bootstrap_servers,
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                key_serializer=lambda x: x.encode('utf-8') if x else None,
                acks='all',  # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,
                compression_type='gzip'
            )
            logger.info(f"✅ Kafka Producer created: {self.settings.kafka.bootstrap_servers}")
            return producer
        except KafkaError as e:
            logger.error(f"❌ Failed to create Kafka Producer: {e}")
            raise
    
    def _on_send_success(self, record_metadata):
        """Callback for successful send"""
        self.stats['sent'] += 1
        if self.stats['sent'] % 100 == 0:
            logger.info(f"📊 Sent {self.stats['sent']} messages (Failed: {self.stats['failed']})")
    
    def _on_send_error(self, exception):
        """Callback for failed send"""
        self.stats['failed'] += 1
        logger.error(f"❌ Message failed: {exception}")
    
    def _filter_event(self, event: Dict[str, Any]) -> bool:
        """
        Filter events to reduce noise
        Returns True if event should be processed
        """
        # Skip certain namespaces (talk pages, user pages, etc.)
        skip_namespaces = ['talk', 'user_talk', 'wikipedia_talk']
        namespace = str(event.get('namespace', '')).lower()
        
        if any(skip in namespace for skip in skip_namespaces):
            self.stats['skipped'] += 1
            return False
        
        # Only process certain event types
        valid_types = ['edit', 'new', 'log']
        if event.get('type') not in valid_types:
            self.stats['skipped'] += 1
            return False
        
        return True
    
    def _enrich_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich event with additional fields for analytics
        """
        enriched = event.copy()
        
        # Add derived fields
        enriched['is_bot'] = event.get('bot', False)
        enriched['is_minor'] = event.get('minor', False)
        enriched['is_new_page'] = event.get('type') == 'new'
        
        # Calculate change size (for traffic volume analysis)
        length_old = event.get('length', {}).get('old', 0) if isinstance(event.get('length'), dict) else 0
        length_new = event.get('length', {}).get('new', 0) if isinstance(event.get('length'), dict) else 0
        enriched['bytes_changed'] = abs(length_new - length_old)
        
        # Extract geo info if available
        if 'server_name' in event:
            # server_name format: en.wikipedia.org -> language: en, project: wikipedia
            parts = event['server_name'].split('.')
            if len(parts) >= 2:
                enriched['language'] = parts[0]
                enriched['project'] = parts[1] if len(parts) > 1 else 'unknown'
        
        return enriched
    
    def start(self, max_messages: Optional[int] = None):
        """
        Start producing messages from Wikimedia stream
        
        Args:
            max_messages: Maximum number of messages to send (None = unlimited)
        """
        self.producer = self._create_producer()
        
        headers = {
            'User-Agent': self.settings.wiki_api.user_agent
        }
        
        logger.info(f"📡 Connecting to {self.settings.wiki_api.stream_url}")
        logger.info(f"🚀 Publishing to Kafka topic: '{self.settings.kafka.topic_name}'")
        logger.info(f"🎯 Max messages: {max_messages or 'Unlimited'}")
        
        try:
            with requests.get(
                self.settings.wiki_api.stream_url,
                stream=True,
                headers=headers,
                timeout=self.settings.wiki_api.timeout
            ) as response:
                
                if response.status_code != 200:
                    logger.error(f"❌ Connection failed: HTTP {response.status_code}")
                    return
                
                logger.info("✅ Connected! Streaming started (Ctrl+C to stop)...")
                
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        
                        # SSE format: "data: {json}"
                        if decoded_line.startswith("data: "):
                            json_str = decoded_line[6:]
                            try:
                                event = json.loads(json_str)
                                
                                # Filter unwanted events
                                if not self._filter_event(event):
                                    continue
                                
                                # Enrich event
                                enriched_event = self._enrich_event(event)
                                
                                # Send to Kafka (async)
                                # Use server_name as key for partitioning
                                key = enriched_event.get('server_name', 'unknown')
                                
                                self.producer.send(
                                    self.settings.kafka.topic_name,
                                    value=enriched_event,
                                    key=key
                                ).add_callback(self._on_send_success).add_errback(self._on_send_error)
                                
                                # Check if we've reached the limit
                                if max_messages and self.stats['sent'] >= max_messages:
                                    logger.info(f"✅ Reached max messages limit: {max_messages}")
                                    break
                                
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ Invalid JSON: {e}")
                                continue
                            except Exception as e:
                                import traceback
                                logger.error(f"❌ Error processing event: {e}")
                                logger.error(traceback.format_exc())
                                logger.error(f"Event data: {event}")
                                continue
        
        except KeyboardInterrupt:
            logger.info("\n🛑 Stopping producer...")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Connection error: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
        finally:
            self._shutdown()
    
    def _shutdown(self):
        """Clean shutdown"""
        if self.producer:
            logger.info("⏳ Flushing remaining messages...")
            self.producer.flush(timeout=10)
            self.producer.close()
            logger.info("✅ Producer closed")
        
        # Print final stats
        logger.info("\n" + "="*60)
        logger.info("📊 Final Statistics:")
        logger.info(f"   ✅ Sent: {self.stats['sent']}")
        logger.info(f"   ❌ Failed: {self.stats['failed']}")
        logger.info(f"   ⏭️  Skipped: {self.stats['skipped']}")
        logger.info(f"   📦 Total processed: {sum(self.stats.values())}")
        logger.info("="*60)


def main():
    """Entry point for running producer standalone"""
    producer = WikiProducer()
    producer.start()


if __name__ == "__main__":
    main()

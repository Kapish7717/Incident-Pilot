from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter('request_count', 'Total number of requests')
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Latency of requests in seconds')
ERROR_COUNT = Counter('error_count', 'Total number of errors')
MEMORY_USAGE = Gauge('memory_usage_bytes', 'Memory usage in bytes')
CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')

# Detailed/Type-specific Custom Metrics
APP_ERRORS_TOTAL = Counter('app_errors_total', 'Detailed application error count', ['type', 'endpoint'])
DB_CONNECTION_FAILURES = Counter('db_connection_failures_total', 'Total failed DB queries/connections')
LLM_TIMEOUT = Counter('llm_timeout_total', 'Total LLM timeout failures')
RAG_RETRIEVAL_FAILURES = Counter('rag_retrieval_failures_total', 'Total RAG retrieval failures')
INVALID_INPUT_ERRORS = Counter('invalid_input_errors_total', 'Total invalid input errors')
EXTERNAL_API_FAILURES = Counter('external_api_failures_total', 'Total external API failures')


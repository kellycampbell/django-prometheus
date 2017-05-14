
from prometheus_client import Counter, Histogram
from django_prometheus.utils import Time, TimeSince, TimeBuckets, PowersOf


connections_total = Counter(
    'django_db_new_connections_total',
    'Counter of created connections by database and by vendor.',
    ['alias', 'vendor'])

connection_errors_total = Counter(
    'django_db_new_connection_errors_total',
    'Counter of connection failures by database and by vendor.',
    ['alias', 'vendor'])


execute_total = Counter(
    'django_db_execute_total',
    'Counter of executed statements by view, database, including bulk executions.',
    ['view', 'alias'])

execute_duration = Histogram(
    'django_db_execute_duration_seconds',
    'Histogram of duration of db query execution by view, database',
    ['view', 'alias'],
    buckets=TimeBuckets())

execute_many_total = Counter(
    'django_db_execute_many_total',
    'Counter of executed statements in bulk operations by view and database.',
    ['view', 'alias'],
    buckets=TimeBuckets())

execute_many_duration = Histogram(
    'django_db_execute_many_duration_seconds',
    'Histogram of duration of bulk db query execution by view, database',
    ['view', 'alias'],
    buckets=TimeBuckets())

errors_total = Counter(
    'django_db_errors_total',
    'Counter of execution errors by database, vendor and exception type.',
    ['view', 'alias', 'type'])


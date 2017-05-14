from __future__ import absolute_import, unicode_literals

from time import time

from django_prometheus.utils import Time, TimeSince, TimeBuckets, PowersOf


# def get_new_connection(self, *args, **kwargs):
#     connections_total.labels(self.alias, self.vendor).inc()
#     try:
#         return super(DatabaseWrapperMixin, self).get_new_connection(
#             *args, **kwargs)
#     except:
#         connection_errors_total.labels(self.alias, self.vendor).inc()
#         raise


def wrap_cursor(connection, recorder):
    if not hasattr(connection, '_djprom_original_cursor'):
        connection._djprom_original_cursor = connection.cursor

        def cursor(*args, **kwargs):
            # Per the DB API cursor() does not accept any arguments. There's
            # some code in the wild which does not follow that convention,
            # so we pass on the arguments even though it's not clean.
            # See:
            # https://github.com/jazzband/django-debug-toolbar/pull/615
            # https://github.com/jazzband/django-debug-toolbar/pull/896
            return CursorWrapper(connection._djprom_original_cursor(*args, **kwargs), connection, recorder)

        connection.cursor = cursor
        return cursor


def unwrap_cursor(connection):
    if hasattr(connection, '_djprom_original_cursor'):
        del connection._djprom_original_cursor
        del connection.cursor


class ExceptionCounterByType(object):
    """A context manager that counts exceptions by type.

    Exceptions increment the provided counter, whose last label's name
    must match the `type_label` argument.

    In other words:

    c = Counter('http_request_exceptions_total', 'Counter of exceptions',
                ['method', 'type'])
    with ExceptionCounterByType(c, extra_labels={'method': 'GET'}):
        handle_get_request()
    """

    def __init__(self, counter):
        self._counter = counter

    def __enter__(self):
        pass

    def __exit__(self, typ, value, traceback):
        if typ is not None:
            self._counter.inc_exceptions(typ.__name__)


class CursorWrapper(object):
    """
    Wraps a cursor and logs queries.
    """

    def __init__(self, cursor, db, recorder):
        self.cursor = cursor
        # Instance of a BaseDatabaseWrapper subclass
        self.db = db
        self.recorder = recorder


    def _record(self, bulk, method, sql, params):
        self._exceptions = {} # type: count
        start_time = Time()
        try:
            with ExceptionCounterByType(self):
                return method(sql, params)
        finally:
            time_since = TimeSince(start_time)

            alias = getattr(self.db, 'alias', 'default')
            conn = self.db.connection

            record_params = {
                'alias': alias,
                'duration': time_since,
                # 'is_select': sql.lower().strip().startswith('select'),
                'is_bulk': bulk
            }
            if bulk:
                record_params['bulk_items_count'] = len(params)
            if len(self._exceptions):
                record_params['exceptions'] = self._exceptions

            self.recorder.record(record_params)


    def inc_exceptions(self, ex_type):
        if ex_type in self._exceptions:
            self._exceptions[ex_type] = self._exceptions[ex_type] + 1
        else:
            self._exceptions[ex_type] = 1


    def callproc(self, procname, params=None):
        return self._record(False, self.cursor.callproc, procname, params)


    def execute(self, sql, params=None):
        return self._record(False, self.cursor.execute, sql, params)


    def executemany(self, sql, param_list):
        return self._record(True, self.cursor.executemany, sql, param_list)


    def __getattr__(self, attr):
        return getattr(self.cursor, attr)


    def __iter__(self):
        return iter(self.cursor)


    def __enter__(self):
        return self


    def __exit__(self, type, value, traceback):
        self.close()

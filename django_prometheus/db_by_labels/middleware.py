from __future__ import absolute_import, unicode_literals

import re
import threading

from django.conf import settings
from django.db import connections

from django.utils import six
from django.utils.encoding import force_text
from django.utils.lru_cache import lru_cache
from django.utils.module_loading import import_string

from .cursor_wrapper import wrap_cursor, unwrap_cursor
from .metrics import *

import logging
log = logging.getLogger('django_prometheus.db_by_labels.middleware')


try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:  # Django < 1.10
    # Works perfectly for everyone using MIDDLEWARE_CLASSES
    MiddlewareMixin = object


class Recording(object):

    def __init__(self, request):
        self.request = request
        self.view_name = ''
        self.records = []


    def start(self):
        # This is thread-safe because database connections are thread-local.
        for connection in connections.all():
            wrap_cursor(connection, self)


    def stop(self):
        for connection in connections.all():
            unwrap_cursor(connection)
        self.update_metrics()


    def record(self, params):
        self.records.append(params)


    def update_metrics(self):
        # naive implementation, just run through each record and inc metrics
        # TODO: pre-analyze records to group and increment metrics at the end
        for record in self.records:
            alias = record['alias']
            duration = record['duration']
            execute_total.labels(self.view_name, alias).inc()
            execute_duration.labels(self.view_name, alias).observe(duration)
            if record['is_bulk']:
                execute_many_total.labels(self.view_name, alias).inc()
                execute_many_item_total.labels(self.view_name, alias).inc(record['bulk_items_count'])
                execute_many_duration.labels(self.view_name, alias).observe(duration)
            if 'exceptions' in record:
                for (ex_type, count) in record['exceptions'].iteritems():
                    errors_total.labels(self.view_name, alias, ex_type).inc(count)


class PrometheusDatabaseMiddleware(MiddlewareMixin):
    """
    Middleware to setup for recording db metrics on incoming request
    and then adding them to the metrics on outgoing response.
    """

    recordings = {}


    def process_request(self, request):
        recording = Recording(request)
        self.__class__.recordings[threading.current_thread().ident] = recording

        recording.start()


    def process_view(self, request, view_func, view_args, view_kwargs):
        recording = self.__class__.recordings[threading.current_thread().ident]
        name = request.resolver_match.view_name or '<unnamed view>'
        recording.view_name = name


    def process_response(self, request, response):
        recording = self.__class__.recordings.pop(threading.current_thread().ident, None)
        if not recording:
            return response

        recording.stop()

        self.check_hanging_transactions(recording.view_name)
        return response

    def check_hanging_transactions(self, view_name):
        for connection in connections.all():
            if connection.in_atomic_block:
                log.warning("Connection still in atomic block: view=%s, connection=%r", view_name, connection)
            if  connection.commit_on_exit == False:
                log.warning("connection.commit_on_exit is False: view=%s, connection=%r", view_name, connection)
            if  connection.allow_thread_sharing == True:
                log.warning("connection.allow_thread_sharing is True: view=%s, connection=%r", view_name, connection)

        # self.autocommit = False
        # # Tracks if the connection is in a transaction managed by 'atomic'.
        # self.in_atomic_block = False
        # # Increment to generate unique savepoint ids.
        # self.savepoint_state = 0
        # # List of savepoints created by 'atomic'.
        # self.savepoint_ids = []
        # # Tracks if the outermost 'atomic' block should commit on exit,
        # # ie. if autocommit was active on entry.
        # self.commit_on_exit = True
        # # Tracks if the transaction should be rolled back to the next
        # # available savepoint because of an exception in an inner block.
        # self.needs_rollback = False

        # # Connection termination related attributes.
        # self.close_at = None
        # self.closed_in_transaction = False
        # self.errors_occurred = False
        # Thread-safety related attributes.
        # self.allow_thread_sharing = allow_thread_sharing
        # self.run_on_commit = []

        # # Should we run the on-commit hooks the next time set_autocommit(True)
        # # is called?
        # self.run_commit_hooks_on_set_autocommit_on = False

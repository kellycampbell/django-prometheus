from django.apps import AppConfig
# unused import to force instantiating the metric objects at startup.
import django_prometheus


class DjangoPrometheusConfig(AppConfig):
    name = 'django_prometheus'
    verbose_name = 'Django-Prometheus'

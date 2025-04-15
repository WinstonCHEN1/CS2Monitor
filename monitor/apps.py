from django.apps import AppConfig


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"

    def ready(self):
        # 导入模板标签库以确保它们被注册
        import monitor.templatetags.monitor_extras

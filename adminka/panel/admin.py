from django.contrib import admin
from django.db.models import Count

from .models import BotUser, Reminder

admin.site.site_header = "🔔 EslatBot — Adminka"
admin.site.site_title = "EslatBot"
admin.site.index_title = "Boshqaruv paneli"


class ReminderInline(admin.TabularInline):
    model = Reminder
    extra = 0
    fields = ("text", "freq", "weekday", "monthday", "hour", "minute", "is_active")
    show_change_link = True


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "tg_id", "reminders_count", "created_at")
    search_fields = ("name", "tg_id")
    ordering = ("-id",)
    inlines = [ReminderInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_rc=Count("reminders"))

    @admin.display(description="Eslatmalari", ordering="_rc")
    def reminders_count(self, obj):
        return obj._rc


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("id", "text", "user", "freq", "vaqti", "is_active", "created_at")
    list_filter = ("freq", "is_active")
    search_fields = ("text", "user__name", "user__tg_id")
    list_editable = ("is_active",)
    ordering = ("-id",)

    @admin.display(description="Vaqti")
    def vaqti(self, obj):
        return obj.time_str

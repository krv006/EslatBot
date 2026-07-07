from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import BotUser, Reminder

admin.site.site_header = "🔔 EslatBot — Adminka"
admin.site.site_title = "EslatBot"
admin.site.index_title = "Boshqaruv paneli"


class ReminderInline(admin.TabularInline):
    model = Reminder
    extra = 0
    fields = ("text", "freq", "weekday", "monthday", "hour", "minute", "is_active")
    show_change_link = True
    verbose_name_plural = "Bu foydalanuvchining eslatmalari"


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "last_name", "tg_username", "phone_display", "tg_id",
        "language_code", "is_premium", "registered", "reminders_count",
        "created_at", "last_seen",
    )
    list_filter = ("registered", "is_premium", "language_code")
    search_fields = ("name", "last_name", "username", "phone", "tg_id")
    ordering = ("-id",)
    inlines = [ReminderInline]
    readonly_fields = ("tg_id", "created_at", "last_seen")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_rc=Count("reminders"))

    @admin.display(description="TG username")
    def tg_username(self, obj):
        if obj.username:
            return format_html(
                '<a href="https://t.me/{}" target="_blank">@{}</a>',
                obj.username, obj.username,
            )
        return "—"

    @admin.display(description="Telefon", ordering="phone")
    def phone_display(self, obj):
        if obj.phone:
            phone = obj.phone if obj.phone.startswith("+") else f"+{obj.phone}"
            return format_html('<a href="tel:{}">{}</a>', phone, phone)
        return "—"

    @admin.display(description="Eslatmalari", ordering="_rc")
    def reminders_count(self, obj):
        return obj._rc


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "text", "user", "user_phone", "freq", "vaqti",
        "is_active", "created_at",
    )
    list_filter = ("freq", "is_active")
    search_fields = ("text", "user__name", "user__username", "user__phone", "user__tg_id")
    list_editable = ("is_active",)
    ordering = ("-id",)
    list_select_related = ("user",)

    @admin.display(description="Vaqti")
    def vaqti(self, obj):
        return obj.time_str

    @admin.display(description="Egasining telefoni")
    def user_phone(self, obj):
        return obj.user.phone or "—"

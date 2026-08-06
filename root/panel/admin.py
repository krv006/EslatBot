from datetime import date, datetime, timedelta

from django.contrib import admin
from django.db import connection
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import BotUser, Referral, Reminder

admin.site.site_header = "🔔 EslatBot — Adminka"
admin.site.site_title = "EslatBot"
admin.site.index_title = "Boshqaruv paneli"


# =====================================================================
# Bosh sahifadagi statistika paneli (dashboard)
# =====================================================================

def _scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def get_dashboard_stats() -> dict | None:
    """Bosh sahifa uchun umumiy statistika. Xato bo'lsa (jadval yo'q) — None."""
    today = date.today().isoformat()
    week_start = (date.today() - timedelta(days=6)).isoformat()
    # Faollik chegaralari (last_seen — oxirgi interaksiya vaqti, ISO satr)
    now = datetime.now()
    d7 = (now - timedelta(days=7)).isoformat()
    d30 = (now - timedelta(days=30)).isoformat()
    try:
        with connection.cursor() as cur:
            stats = {
                "users_total": _scalar(cur, "SELECT COUNT(*) FROM users"),
                "users_registered": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE registered=1"),
                "users_today": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)=%s",
                    [today]),
                "users_week": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)>=%s",
                    [week_start]),
                "users_premium": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE is_premium=1"),
                "digest_on": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE digest_enabled=1"),
                "rem_total": _scalar(cur, "SELECT COUNT(*) FROM reminders"),
                "rem_active": _scalar(
                    cur, "SELECT COUNT(*) FROM reminders WHERE is_active=1"),
                # --- Faollik (last_seen bo'yicha) ---
                "active_7": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE last_seen >= %s", [d7]),
                "active_30": _scalar(
                    cur, "SELECT COUNT(*) FROM users WHERE last_seen >= %s", [d30]),
                "inactive_30": _scalar(
                    cur,
                    "SELECT COUNT(*) FROM users "
                    "WHERE last_seen IS NULL OR last_seen < %s", [d30]),
            }
            # Sust = 7–30 kun oralig'ida ko'ringanlar
            stats["sust"] = max(stats["active_30"] - stats["active_7"], 0)
            # Takror turlari bo'yicha (faol eslatmalar)
            cur.execute(
                "SELECT freq, COUNT(*) FROM reminders WHERE is_active=1 GROUP BY freq")
            freq_names = {
                "once": "📌 Bir marta", "daily": "📅 Har kuni",
                "every2": "🔁 Kun ora", "weekly": "📆 Haftada bir",
                "monthly": "🗓 Oyda bir",
            }
            stats["by_freq"] = [
                (freq_names.get(f, f), c) for f, c in cur.fetchall()
            ]
            # Referallar (jadval hali yaratilmagan bo'lishi mumkin — himoyalaymiz)
            try:
                stats["ref_total"] = _scalar(cur, "SELECT COUNT(*) FROM referrals")
                stats["ref_claimed"] = _scalar(
                    cur, "SELECT COUNT(*) FROM referrals WHERE claimed_count>=1")
            except Exception:
                stats["ref_total"] = stats["ref_claimed"] = 0
        return stats
    except Exception:
        return None


_orig_index = admin.site.index


def _index_with_stats(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context["dashboard_stats"] = get_dashboard_stats()
    return _orig_index(request, extra_context)


admin.site.index = _index_with_stats
admin.site.index_template = "admin/eslat_index.html"


class UserActivityFilter(admin.SimpleListFilter):
    """last_seen (oxirgi faollik) bo'yicha faol/sust/nofaol filtri."""
    title = "Faollik holati"
    parameter_name = "faollik"

    def lookups(self, request, model_admin):
        return [
            ("faol", "🟢 Faol (7 kun ichida)"),
            ("sust", "🟡 Sust (7–30 kun)"),
            ("nofaol", "🔴 Nofaol (30+ kun / hech qachon)"),
        ]

    def queryset(self, request, queryset):
        now = datetime.now()
        d7 = now - timedelta(days=7)
        d30 = now - timedelta(days=30)
        v = self.value()
        if v == "faol":
            return queryset.filter(last_seen__gte=d7)
        if v == "sust":
            return queryset.filter(last_seen__gte=d30, last_seen__lt=d7)
        if v == "nofaol":
            return queryset.filter(Q(last_seen__lt=d30) | Q(last_seen__isnull=True))
        return queryset


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
        "faollik", "language_code", "is_premium", "registered", "digest_display",
        "reminders_count", "created_at", "last_seen",
    )
    list_filter = (
        UserActivityFilter, "registered", "is_premium", "digest_enabled",
        "language_code",
    )
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

    @admin.display(description="🌅 Digest")
    def digest_display(self, obj):
        if obj.digest_enabled:
            return f"✅ {obj.digest_hour or 7:02d}:{obj.digest_minute or 0:02d}"
        return "🔕"

    @admin.display(description="Faollik", ordering="last_seen")
    def faollik(self, obj):
        if not obj.last_seen:
            return format_html('<span style="color:#ef4444">🔴 Hech qachon</span>')
        days = (datetime.now() - obj.last_seen).days
        if days <= 7:
            label = "bugun" if days == 0 else f"{days} kun oldin"
            return format_html(
                '<span style="color:#22c55e">🟢 Faol</span>'
                '<br><small style="color:#9ca3af">{}</small>', label)
        if days <= 30:
            return format_html(
                '<span style="color:#f59e0b">🟡 Sust</span>'
                '<br><small style="color:#9ca3af">{} kun oldin</small>', days)
        return format_html(
            '<span style="color:#ef4444">🔴 Nofaol</span>'
            '<br><small style="color:#9ca3af">{} kun oldin</small>', days)

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


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        "id", "text", "from_user", "from_phone", "freq", "vaqti",
        "holat", "created_at",
    )
    list_filter = ("freq", "claimed_count")
    search_fields = (
        "text", "token", "from_user__name", "from_user__username",
        "from_user__phone", "from_user__tg_id",
    )
    ordering = ("-id",)
    list_select_related = ("from_user",)
    readonly_fields = (
        "token", "from_user", "text", "freq", "weekday", "monthday",
        "hour", "minute", "start_date", "created_at", "claimed_count",
    )

    def has_add_permission(self, request):
        return False  # Referallar bot orqali yaratiladi, qo'lda emas

    @admin.display(description="Vaqti")
    def vaqti(self, obj):
        return obj.time_str

    @admin.display(description="Yuboruvchi telefoni")
    def from_phone(self, obj):
        return obj.from_user.phone or "—"

    @admin.display(description="Holat")
    def holat(self, obj):
        if obj.claimed_count and obj.claimed_count >= 1:
            return format_html('<span style="color:#22c55e">✅ Qabul qilingan</span>')
        return format_html('<span style="color:#f59e0b">⏳ Kutilmoqda</span>')

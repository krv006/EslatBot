"""Bot jadvallariga 'oyna' — managed=False, ya'ni Django bu jadvallarni
yaratmaydi va o'zgartirmaydi, faqat o'qiydi/yozadi."""
from django.db import models
from django_ckeditor_5.fields import CKEditor5Field

FREQ_CHOICES = [
    ("once", "📌 Bir marta"),
    ("daily", "📅 Har kuni"),
    ("every2", "🔁 Kun ora"),
    ("weekly", "📆 Haftada bir"),
    ("monthly", "🗓 Oyda bir"),
]

WEEKDAY_CHOICES = [
    (0, "Dushanba"), (1, "Seshanba"), (2, "Chorshanba"), (3, "Payshanba"),
    (4, "Juma"), (5, "Shanba"), (6, "Yakshanba"),
]


class BotUser(models.Model):
    tg_id = models.BigIntegerField("Telegram ID", unique=True)
    name = models.TextField("Ismi", blank=True, null=True)
    last_name = models.TextField("Familiya", blank=True, null=True)
    username = models.TextField("TG username", blank=True, null=True)
    phone = models.TextField("Telefon", blank=True, null=True)
    language_code = models.TextField("Til", blank=True, null=True)
    is_premium = models.BooleanField("Premium", blank=True, null=True)
    registered = models.BooleanField("Ro'yxatdan o'tgan", default=False)
    digest_enabled = models.BooleanField("Digest yoqilgan", default=True)
    digest_hour = models.IntegerField("Digest soati", default=7)
    digest_minute = models.IntegerField("Digest daqiqasi", default=0)
    created_at = models.DateTimeField("Kelgan vaqti", blank=True, null=True)
    last_seen = models.DateTimeField("Oxirgi faollik", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"

    def __str__(self):
        return f"{self.name or 'Nomsiz'} ({self.tg_id})"


class Reminder(models.Model):
    user = models.ForeignKey(
        BotUser, on_delete=models.CASCADE, db_column="user_id",
        related_name="reminders", verbose_name="Foydalanuvchi",
    )
    text = models.TextField("Eslatma matni")
    freq = models.TextField("Takrorlanish", choices=FREQ_CHOICES)
    weekday = models.IntegerField(
        "Hafta kuni", choices=WEEKDAY_CHOICES, blank=True, null=True
    )
    monthday = models.IntegerField("Oy kuni", blank=True, null=True)
    hour = models.IntegerField("Soat")
    minute = models.IntegerField("Daqiqa")
    start_date = models.TextField(blank=True, null=True)
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField("Yaratilgan", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "reminders"
        verbose_name = "Eslatma"
        verbose_name_plural = "Eslatmalar"

    def __str__(self):
        return self.text[:50]

    @property
    def time_str(self):
        return f"{self.hour:02d}:{self.minute:02d}"


BROADCAST_TARGET_CHOICES = [
    ("all", "📢 Hammaga (barcha foydalanuvchilar)"),
    ("username", "👤 Bitta userga — username bo'yicha"),
    ("phone", "📱 Bitta userga — telefon bo'yicha"),
]

BROADCAST_STATUS_CHOICES = [
    ("pending", "⏳ Navbatda"),
    ("sending", "📤 Yuborilmoqda"),
    ("done", "✅ Yuborildi"),
    ("error", "❌ Xato"),
]


class Broadcast(models.Model):
    """Admin paneldan yuboriladigan xabar. Django faqat 'pending' yozadi;
    haqiqiy yuborishni bot jarayoni (flood-himoyali sender) bajaradi."""
    text = CKEditor5Field("Xabar matni", config_name="broadcast")
    target = models.TextField(
        "Kimga", choices=BROADCAST_TARGET_CHOICES, default="all")
    target_value = models.TextField(
        "Username yoki Telefon", blank=True, null=True,
        help_text="Faqat 'username' yoki 'telefon' tanlaganda to'ldiring. "
                  "Masalan: @ali yoki +998901234567",
    )
    status = models.TextField(
        "Holat", choices=BROADCAST_STATUS_CHOICES, default="pending")
    total = models.IntegerField("Jami qabul qiluvchi", default=0)
    sent = models.IntegerField("Yuborildi", default=0)
    failed = models.IntegerField("Yetib bormadi", default=0)
    error = models.TextField("Xato izohi", blank=True, null=True)
    created_at = models.DateTimeField("Yaratilgan", auto_now_add=True)
    sent_at = models.DateTimeField("Yuborilgan vaqti", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "broadcasts"
        verbose_name = "Xabar yuborish"
        verbose_name_plural = "📢 Xabar yuborish"

    def __str__(self):
        return f"#{self.id} — {self.get_target_display()} [{self.status}]"


class Referral(models.Model):
    """Referal — bir user eslatmani boshqaga ulashgani (users.referrals jadvali)."""
    token = models.TextField("Havola tokeni")
    from_user = models.ForeignKey(
        BotUser, on_delete=models.CASCADE, db_column="from_user_id",
        related_name="referrals_sent", verbose_name="Yuboruvchi",
    )
    text = models.TextField("Eslatma matni")
    freq = models.TextField("Takrorlanish", choices=FREQ_CHOICES)
    weekday = models.IntegerField(
        "Hafta kuni", choices=WEEKDAY_CHOICES, blank=True, null=True
    )
    monthday = models.IntegerField("Oy kuni", blank=True, null=True)
    hour = models.IntegerField("Soat")
    minute = models.IntegerField("Daqiqa")
    start_date = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField("Yaratilgan", blank=True, null=True)
    claimed_count = models.IntegerField("Qabul soni", default=0)

    class Meta:
        managed = False
        db_table = "referrals"
        verbose_name = "Referal"
        verbose_name_plural = "Referallar"

    def __str__(self):
        return self.text[:50]

    @property
    def time_str(self):
        return f"{self.hour:02d}:{self.minute:02d}"

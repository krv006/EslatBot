"""Bot jadvallariga 'oyna' — managed=False, ya'ni Django bu jadvallarni
yaratmaydi va o'zgartirmaydi, faqat o'qiydi/yozadi."""
from django.db import models

FREQ_CHOICES = [
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

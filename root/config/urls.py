import os

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path

# Xavfsizlik: admin manzilini .env orqali o'zgartirsa bo'ladi
# (masalan DJANGO_ADMIN_URL=boshqaruv-x7/ — avtomatik hujumlarga qarshi)
ADMIN_URL = os.getenv("DJANGO_ADMIN_URL", "admin/")
if not ADMIN_URL.endswith("/"):
    ADMIN_URL += "/"

urlpatterns = [
    path("", lambda request: redirect(ADMIN_URL)),
    path(ADMIN_URL, admin.site.urls),
]

"""Mini App URL'lari — sahifa va JSON API."""
from django.urls import path

from . import views

app_name = "webapp"

urlpatterns = [
    path("", views.index, name="index"),
    # --- API ---
    path("api/bootstrap", views.bootstrap, name="bootstrap"),
    path("api/reminders", views.reminders, name="reminders"),
    path("api/reminders/<int:pk>", views.reminder_detail, name="reminder_detail"),
    path("api/tasks", views.tasks, name="tasks"),
    path("api/tasks/<int:pk>", views.task_detail, name="task_detail"),
    path("api/notes", views.notes, name="notes"),
    path("api/notes/<int:pk>", views.note_detail, name="note_detail"),
    path("api/materials", views.materials, name="materials"),
    path("api/materials/<int:pk>", views.material_detail, name="material_detail"),
    path("api/settings", views.settings_view, name="settings"),
]

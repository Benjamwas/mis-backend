from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("lms", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Quiz",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("title", models.CharField(max_length=200)),
                ("instructions", models.TextField(blank=True, default="")),
                ("questions", models.JSONField(default=list)),
                ("max_attempts", models.PositiveIntegerField(default=2)),
                ("pass_percentage", models.PositiveIntegerField(default=60)),
                ("time_limit_minutes", models.PositiveIntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("CLOSED", "Closed")], db_index=True, default="DRAFT", max_length=12)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_quizzes", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="schools.school")),
                ("topic", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quizzes", to="lms.topic")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="QuizAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("answers", models.JSONField(default=list)),
                ("score", models.PositiveIntegerField(default=0)),
                ("percentage", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("status", models.CharField(choices=[("IN_PROGRESS", "In Progress"), ("SUBMITTED", "Submitted")], db_index=True, default="IN_PROGRESS", max_length=15)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("quiz", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="lms.quiz")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="schools.school")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quiz_attempts", to="people.student")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="quizattempt",
            constraint=models.UniqueConstraint(fields=("quiz", "student", "attempt_number"), name="uq_quiz_student_attempt"),
        ),
    ]

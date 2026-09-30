from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("academics", "0002_initial")]

    operations = [
        migrations.CreateModel(
            name="StudentGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="schools.school")),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("ARCHIVED", "Archived")], db_index=True, default="ACTIVE", max_length=12)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_student_groups", to=settings.AUTH_USER_MODEL)),
                ("school_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_groups", to="schools.schoolclass")),
                ("subject", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="student_groups", to="academics.subject")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StudentGroupMember",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_leader", models.BooleanField(default=False)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="members", to="academics.studentgroup")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_groups", to="people.student")),
            ],
        ),
        migrations.AddConstraint(
            model_name="studentgroupmember",
            constraint=models.UniqueConstraint(fields=("group", "student"), name="uq_student_group_member"),
        ),
    ]

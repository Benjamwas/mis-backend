from rest_framework import serializers

from apps.attendance.models import AttendanceSession, EmployeeAttendance, StudentAttendance


class AttendanceSessionSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.display_name", read_only=True)

    class Meta:
        model = AttendanceSession
        fields = ["id", "school", "school_class", "class_name", "term", "attendance_date",
                  "recorded_by", "remarks", "status", "created_at"]
        read_only_fields = ["school", "recorded_by", "status"]


class StudentAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentAttendance
        fields = ["id", "school", "session", "student", "student_name", "status", "remarks"]
        read_only_fields = ["school"]


class EmployeeAttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.person.full_name", read_only=True)

    class Meta:
        model = EmployeeAttendance
        fields = ["id", "school", "employee", "employee_name", "attendance_date",
                  "clock_in", "clock_out", "status", "remarks"]
        read_only_fields = ["school"]
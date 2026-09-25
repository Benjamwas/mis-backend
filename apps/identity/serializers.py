from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.identity.models import Person, Role, RoleCode, UserRole

User = get_user_model()


class PersonSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = ["id", "first_name", "middle_name", "last_name", "full_name",
                  "date_of_birth", "gender", "phone", "email", "address", "photo_url"]


class UserSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "status", "full_name", "person", "last_login_at", "created_at", "is_staff", "is_superuser"]
        read_only_fields = ["status", "last_login_at", "created_at"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "code", "description", "is_system", "permissions"]

    def get_permissions(self, obj):
        return [p.code for p in obj.permissions.all()]


class UserRoleSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    role_code = serializers.ChoiceField(choices=RoleCode.choices, write_only=True)
    school_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = UserRole
        fields = ["id", "role", "role_code", "school_id", "school"]

    def create(self, validated_data):
        return UserRole.objects.create(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    middle_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    photo_url = serializers.URLField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=Person.Gender.choices, required=False)

    def update(self, user, validated_data):
        person_fields = ["first_name", "middle_name", "last_name", "phone", "address", "photo_url", "gender"]
        person_updates = {k: v for k, v in validated_data.items() if k in person_fields}
        if person_updates:
            for k, v in person_updates.items():
                setattr(user.person, k, v)
            user.person.save()
        return user
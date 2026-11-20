from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class BaseUser(AbstractUser):
    """Inheritance: Django authentication plus a common interface for five roles."""
    class Role(models.TextChoices):
        STUDENT = 'Student'
        TEACHER = 'Teacher'
        ADMIN = 'Admin'
        FINANCE = 'Finance'
        PRINCIPAL = 'Principal'

    role = models.CharField(max_length=12, choices=Role.choices)

    def dashboard_profile(self):
        profiles = {cls.__name__: cls for cls in (Student, Teacher, Admin, Finance, Principal)}
        profile = profiles.get(self.role)
        if profile is None:
            raise PermissionDenied
        return profile.objects.get(pk=self.pk)

    def get_dashboard_context(self, filters):
        raise NotImplementedError


# Proxy inheritance shares the authentication table while keeping each role's
# dashboard implementation independently overridable.
class Student(BaseUser):
    class Meta:
        proxy = True

    def get_dashboard_context(self, filters):
        from .services import student_context
        return student_context(self)


class Teacher(BaseUser):
    class Meta:
        proxy = True

    def get_dashboard_context(self, filters):
        from .services import teacher_context
        return teacher_context(self)


class Admin(BaseUser):
    class Meta:
        proxy = True

    def get_dashboard_context(self, filters):
        from .services import admin_context
        return admin_context(filters)


class Finance(BaseUser):
    class Meta:
        proxy = True

    def get_dashboard_context(self, filters):
        from .services import finance_context
        return finance_context(filters)


class Principal(BaseUser):
    class Meta:
        proxy = True

    def get_dashboard_context(self, filters):
        from .services import principal_context
        return principal_context(filters)


class Classroom(models.Model):
    name = models.CharField(max_length=60, unique=True)
    teacher = models.ForeignKey(BaseUser, on_delete=models.PROTECT, related_name='classes')
    qr_code = models.CharField(max_length=40, unique=True)


class StudentRecord(models.Model):
    user = models.OneToOneField(BaseUser, on_delete=models.CASCADE, related_name='record')
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name='students')
    blood_group = models.CharField(max_length=8, blank=True)
    allergies = models.CharField(max_length=160, blank=True)
    debate = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    sports = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])


class TeacherPayroll(models.Model):
    teacher = models.ForeignKey(BaseUser, on_delete=models.PROTECT)
    month = models.DateField()
    _salary = models.PositiveIntegerField(db_column='salary')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'month'], name='one_payroll_per_month')]

    # Encapsulation: protected persistence, private working value and role-gated methods.
    def get_salary(self, actor):
        if actor.role not in (BaseUser.Role.FINANCE, BaseUser.Role.PRINCIPAL):
            raise PermissionDenied
        self.__salary = self._salary
        return self.__salary

    def set_salary(self, actor, amount):
        if actor.role != BaseUser.Role.FINANCE:
            raise PermissionDenied
        if amount < 0:
            raise ValidationError('Salary must be nonnegative.')
        self.__salary = amount
        self._salary = self.__salary
        self.save()


class Grade(models.Model):
    student = models.ForeignKey(StudentRecord, on_delete=models.CASCADE, related_name='grades')
    subject = models.CharField(max_length=60)
    score = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    locked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'subject'], name='unique_student_subject'),
            models.CheckConstraint(condition=models.Q(score__lte=100), name='grade_at_most_100'),
        ]

    def _validate_score(self, actor, score):
        if actor.role != BaseUser.Role.TEACHER or self.student.classroom.teacher_id != actor.pk:
            raise PermissionDenied
        if self.locked:
            raise ValidationError('This grade is locked.')
        if not 0 <= score <= 100:
            raise ValidationError('Grade must be between 0 and 100.')

    def set_score(self, actor, score, lock=False):
        self._validate_score(actor, score)
        if self.pk:
            changed = Grade.objects.filter(pk=self.pk, locked=False).update(score=score, locked=lock)
            if not changed:
                raise ValidationError('This grade is locked.')
            self.refresh_from_db()
        else:
            self.score, self.locked = score, lock
            self.save()


class StudentAttendance(models.Model):
    student = models.ForeignKey(StudentRecord, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField()
    present = models.BooleanField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'date'], name='student_attendance_daily')]


class Topic(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=100)
    date = models.DateField()
    status = models.CharField(max_length=12, default='Planned')


class ReviewStatus(models.TextChoices):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'


class CheckIn(models.Model):
    teacher = models.ForeignKey(BaseUser, on_delete=models.PROTECT)
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    photo = models.BinaryField(blank=True, default=bytes, editable=False)
    simulated = models.BooleanField(default=True)


class LeaveRequest(models.Model):
    teacher = models.ForeignKey(BaseUser, on_delete=models.PROTECT)
    date = models.DateField()
    reason = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)


class Fee(models.Model):
    student = models.ForeignKey(StudentRecord, on_delete=models.PROTECT, related_name='fees')
    due_date = models.DateField()
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    paid_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'due_date'], name='one_fee_per_due_date')]


class Issue(models.Model):
    class Tier(models.IntegerChoices):
        LIGHT = 1, 'Silent alert'
        ADMIN = 2, 'Admin queue'
        URGENT = 3, 'Principal escalation'

    author = models.ForeignKey(BaseUser, on_delete=models.PROTECT)
    text = models.CharField(max_length=250)
    tier = models.PositiveSmallIntegerField(choices=Tier.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=70, unique=True, null=True, blank=True)


class Alert(models.Model):
    recipient = models.ForeignKey(BaseUser, on_delete=models.CASCADE)
    channel = models.CharField(max_length=25)
    message = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, null=True)

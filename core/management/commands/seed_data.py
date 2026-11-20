from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Alert, BaseUser, CheckIn, Classroom, Fee, Grade, Issue, LeaveRequest,
    StudentAttendance, StudentRecord, TeacherPayroll, Topic,
)

USERS = [
    ('admin', 'Admin', 'Mariam Hussain'),
    ('principal', 'Principal', 'Nadia Ahmed'),
    ('teacher1', 'Teacher', 'Bilal Khan'),
    ('teacher2', 'Teacher', 'Ayesha Siddiqui'),
    ('finance1', 'Finance', 'Faisal Ali'),
    ('student1', 'Student', 'Amina Shah'),
    ('student2', 'Student', 'Hamza Aziz'),
    ('student3', 'Student', 'Sara Abbas'),
    ('student4', 'Student', 'Zain Raza'),
    ('student5', 'Student', 'Hira Ahmed'),
    ('student6', 'Student', 'Umar Iqbal'),
]


class Command(BaseCommand):
    help = 'Create synthetic demo users and school records.'

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        users = {}
        for username, role, name in USERS:
            first, last = name.split(' ', 1)
            user, created = BaseUser.objects.get_or_create(
                username=username, defaults={'role': role, 'first_name': first, 'last_name': last},
            )
            if user.role != role:
                raise CommandError(f'Username {username} already belongs to a different role.')
            if created:
                user.set_password('pass1234')
                user.save(update_fields=['password'])
            users[username] = user
        rooms = []
        for index, suffix in enumerate(('A', 'B'), start=1):
            room, _ = Classroom.objects.get_or_create(
                name=f'Grade 9 · {suffix}', defaults={'teacher': users[f'teacher{index}'], 'qr_code': f'CLASS-9{suffix}'},
            )
            rooms.append(room)
            for offset, title in enumerate(('Introduction to Python', 'Conditions and loops', 'Functions', 'Lists and tuples', 'Object-oriented programming')):
                Topic.objects.get_or_create(
                    classroom=room, title=title,
                    defaults={'date': today + timedelta(days=offset - 1), 'status': 'Completed' if offset == 0 else 'Planned'},
                )
            if not CheckIn.objects.filter(teacher=room.teacher, classroom=room, simulated=True).exists():
                CheckIn.objects.create(teacher=room.teacher, classroom=room)
            LeaveRequest.objects.get_or_create(
                teacher=room.teacher, reason='University workshop', defaults={'date': today + timedelta(days=5)},
            )
        payroll_months = [today.replace(day=1)]
        for _ in range(5):
            payroll_months.append((payroll_months[-1] - timedelta(days=1)).replace(day=1))
        for index in range(1, 7):
            student, _ = StudentRecord.objects.get_or_create(
                user=users[f'student{index}'],
                defaults={'classroom': rooms[(index - 1) // 3], 'blood_group': ['A+', 'O+', 'B+'][index % 3],
                          'allergies': 'Peanuts' if index == 1 else '', 'debate': 97 - index * 7, 'sports': 55 + index * 6},
            )
            for subject, score in [('Computer Science', 98 - index * 9), ('Mathematics', 96 - index * 11), ('English', 71 + index * 2)]:
                Grade.objects.get_or_create(student=student, subject=subject, defaults={'score': score, 'locked': True})
            for offset in range(5):
                StudentAttendance.objects.get_or_create(
                    student=student, date=today - timedelta(days=offset),
                    defaults={'present': offset < 3 or index % 2 == 0},
                )
            due = today - timedelta(days=1 if index == 1 else 10)
            Fee.objects.get_or_create(
                student=student, due_date=due,
                defaults={'amount': 6500, 'paid_on': today if index % 2 == 0 else None},
            )
            for month in payroll_months[1:]:
                Fee.objects.get_or_create(
                    student=student, due_date=month,
                    defaults={'amount': 6200, 'paid_on': month + timedelta(days=index)},
                )
        for month in payroll_months:
            for index in (1, 2):
                TeacherPayroll.objects.get_or_create(
                    teacher=users[f'teacher{index}'], month=month,
                    defaults={'_salary': 36000 + index * 2500 + month.month * 150},
                )
        for reference, message in (
            ('demo-projector', 'The Grade 9 A projector needs a replacement cable.'),
            ('demo-fan', 'The Grade 9 B ceiling fan needs maintenance.'),
        ):
            Issue.objects.get_or_create(
                reference=reference, defaults={'author': users['teacher1'], 'text': message, 'tier': 2},
            )
        Alert.objects.get_or_create(
            recipient=users['student1'], channel='Portal', message='Your current fee invoice is unpaid.',
        )
        self.stdout.write(self.style.SUCCESS('Demo ready. Sign in with admin, principal, teacher1, student1 or finance1. Password: pass1234'))

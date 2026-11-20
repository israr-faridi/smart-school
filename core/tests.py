from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Alert, BaseUser, CheckIn, Fee, Grade, Issue, LeaveRequest, StudentAttendance, TeacherPayroll, Topic


class DemoWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_data', verbosity=0)

    def login(self, username):
        self.client.force_login(BaseUser.objects.get(username=username))

    def post(self, action, **data):
        return self.client.post(reverse('action', args=[action]), data)

    def test_dashboard_and_demo_credentials_for_each_role(self):
        for user in ('student1', 'teacher1', 'admin', 'finance1', 'principal'):
            with self.subTest(user=user):
                response = self.client.post(reverse('login'), {'username': user, 'password': 'pass1234'})
                self.assertRedirects(response, reverse('dashboard'))
                role = BaseUser.objects.get(username=user).role.lower()
                self.assertTemplateUsed(self.client.get(reverse('dashboard')), f'{role}.html')
                self.client.logout()

    def test_checkin_validation_and_admin_review(self):
        self.login('teacher1')
        teacher = BaseUser.objects.get(username='teacher1')
        room = teacher.classes.get()
        count = CheckIn.objects.count()
        self.post('check-in', classroom=room.pk, qr='wrong', gps='inside', capture='simulated')
        self.assertEqual(CheckIn.objects.count(), count)
        self.post('check-in', classroom=room.pk, qr=room.qr_code, gps='inside', capture='simulated')
        entry = CheckIn.objects.latest('pk')
        self.assertEqual(entry.status, 'Pending')
        self.assertEqual(self.post('review-checkin', id=entry.pk, status='Approved').status_code, 403)
        self.login('admin')
        self.post('review-checkin', id=entry.pk, status='Approved')
        self.post('review-checkin', id=entry.pk, status='Rejected')
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'Approved')
        leave = LeaveRequest.objects.first()
        self.post('review-leave', id=leave.pk, status='Rejected')
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'Rejected')

    def test_syllabus_grades_and_attendance(self):
        self.login('teacher1')
        teacher = BaseUser.objects.get(username='teacher1')
        room = teacher.classes.get()
        missed, following = room.topics.filter(status='Planned').order_by('date')[:2]
        self.post('topic', id=missed.pk, status='Missed')
        self.assertEqual(Topic.objects.get(pk=following.pk).date, following.date + timedelta(days=1))
        self.post('topic', id=missed.pk, status='Missed')
        self.assertEqual(Topic.objects.get(pk=following.pk).date, following.date + timedelta(days=1))
        student = room.students.first()
        self.post('attendance', student=student.pk, present='no')
        self.assertFalse(StudentAttendance.objects.filter(student=student).latest('date').present)
        self.post('grade', student=student.pk, subject='Physics', score=101)
        self.assertFalse(Grade.objects.filter(student=student, subject='Physics').exists())
        self.post('grade', student=student.pk, subject='Physics', score=85, lock='yes')
        self.post('grade', student=student.pk, subject='physics', score=99)
        self.assertEqual(student.grades.get(subject='Physics').score, 85)
        other = BaseUser.objects.get(username='student6').record
        self.assertEqual(self.post('grade', student=other.pk, subject='Physics', score=90).status_code, 404)
        with self.assertRaises(PermissionDenied):
            TeacherPayroll.objects.first().get_salary(teacher)

    def test_fifo_and_notification_channels(self):
        self.login('teacher1')
        for tier in (1, 2, 3):
            self.post('issue', tier=tier, message=f'Tier {tier} demo')
        self.assertTrue(Alert.objects.filter(recipient__username='admin', channel='Portal', message='Tier 1 demo').exists())
        self.assertTrue(Alert.objects.filter(recipient__username='principal', channel='WhatsApp simulation', message='Tier 3 demo').exists())
        first, second = Issue.objects.filter(tier=2).order_by('created_at', 'pk')[:2]
        self.login('admin')
        self.post('resolve', id=second.pk)
        second.refresh_from_db()
        self.assertIsNone(second.resolved_at)
        self.post('resolve', id=first.pk)
        first.refresh_from_db()
        self.assertIsNotNone(first.resolved_at)
        ranked = self.client.get('/dashboard/?scout=sports').context['leaders']
        self.assertEqual([score for _, score in ranked], sorted([score for _, score in ranked], reverse=True))

    def test_finance_lookup_cron_and_transcript(self):
        self.login('finance1')
        self.assertEqual(self.client.get('/dashboard/?student=student1').context['lookup_result'], 'Unpaid')
        self.post('fee-cron')
        count = Alert.objects.count()
        self.assertTrue(Alert.objects.filter(recipient__username='student3', channel='WhatsApp simulation').exists())
        self.post('fee-cron')
        self.assertEqual(Alert.objects.count(), count)
        fee = Fee.objects.get(student__user__username='student1', paid_on=None)
        url = reverse('transcript', args=[fee.student_id])
        response = self.client.get(url)
        self.assertContains(self.client.get(response.context['verification']), 'Signature verified')
        self.assertEqual(self.client.get(response.context['verification'][:-1] + 'z/').status_code, 404)
        self.post('collect', id=fee.pk)
        self.assertEqual(self.client.get('/dashboard/?student=student1').context['lookup_result'], 'Paid')
        self.login('student1')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.post('collect', id=fee.pk).status_code, 403)

from abc import ABC, abstractmethod
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.utils import timezone

from .dsa_engine import DoublyLinkedList, FeeMap, IssueQueue, MaxHeap
from .models import (
    Alert, BaseUser, CheckIn, Classroom, Fee, Grade, Issue, LeaveRequest,
    ReviewStatus, StudentRecord, TeacherPayroll, Topic,
)

Role = BaseUser.Role


# Abstraction: callers use notify() without knowing how alerts are delivered.
class NotificationService(ABC):
    @abstractmethod
    def notify(self, recipients, message, issue=None):
        """Deliver a message through this service's channel."""


class PortalNotifications(NotificationService):
    channel = 'Portal'

    def notify(self, recipients, message, issue=None):
        Alert.objects.bulk_create([
            Alert(recipient=user, channel=self.channel, message=message, issue=issue)
            for user in recipients
        ])


class SimulatedWhatsApp(PortalNotifications):
    channel = 'WhatsApp simulation'

    # Encapsulation: routing details stay inside the simulated integration.
    __principal_contact = 'Local principal inbox'

    def get_principal_contact(self, actor):
        if actor.role != Role.PRINCIPAL:
            raise PermissionDenied
        return self.__principal_contact


@transaction.atomic
def report_issue(author, tier, message):
    issue = Issue.objects.create(author=author, tier=tier, text=message)
    if tier == Issue.Tier.URGENT:
        recipients = BaseUser.objects.filter(role__in=[Role.PRINCIPAL, Role.ADMIN], is_active=True)
        SimulatedWhatsApp().notify(recipients, message, issue)
    elif tier == Issue.Tier.LIGHT:
        PortalNotifications().notify(BaseUser.objects.filter(role=Role.ADMIN, is_active=True), message, issue)
    return issue


def pending_issues():
    return IssueQueue(Issue.objects.filter(tier=2, resolved_at=None).select_related('author').order_by('created_at', 'pk'))


@transaction.atomic
def resolve_next_issue(pk):
    issue = pending_issues().next()
    if issue is None or issue.pk != pk:
        raise ValidationError('Resolve the oldest open issue first.')
    Issue.objects.filter(pk=pk, resolved_at=None).update(resolved_at=timezone.now())


@transaction.atomic
def update_topic(topic, status):
    if status == 'Completed':
        Topic.objects.filter(pk=topic.pk).update(status=status)
        return
    if not Topic.objects.filter(pk=topic.pk, status='Planned').update(status='Missed'):
        raise ValidationError('Only planned topics can be postponed.')
    plan = DoublyLinkedList(Topic.objects.filter(classroom_id=topic.classroom_id).order_by('date', 'pk'))
    Topic.objects.bulk_update(list(plan.postpone(topic.pk)), ['date'])


def scout(filters):
    category = filters.get('scout', 'debate')
    if category not in ('debate', 'sports'):
        category = 'debate'
    students = {student.pk: student for student in StudentRecord.objects.select_related('user', 'classroom').filter(user__is_active=True)}
    heap = MaxHeap((getattr(student, category), -student.pk) for student in students.values())
    leaders = []
    for _ in range(min(5, len(students))):
        score, negative_pk = heap.pop()
        leaders.append((students[-negative_pk], score))
    return {'leaders': leaders, 'category': category}


def student_context(user):
    record = StudentRecord.objects.select_related('classroom').filter(user=user).first()
    if not record:
        return {}
    grades = list(record.grades.order_by('-score', 'subject'))
    streak = 0
    # A streak counts consecutive recorded school days. Weekends need no entries.
    for entry in record.attendance.order_by('-date'):
        if not entry.present:
            break
        streak += 1
    progress = record.classroom.topics.aggregate(total=Count('pk'), complete=Count('pk', filter=Q(status='Completed')))
    return {
        'record': record, 'grades': grades, 'high': grades[0] if grades else None,
        'low': grades[-1] if grades else None, 'streak': streak,
        'progress': round(100 * progress['complete'] / progress['total']) if progress['total'] else 0,
        'topics': record.classroom.topics.order_by('date', 'pk'),
        'unpaid': record.fees.filter(paid_on=None).order_by('due_date'),
    }


def teacher_context(user):
    classes = user.classes.prefetch_related(
        Prefetch('topics', queryset=Topic.objects.order_by('date', 'pk')),
        'students__user', 'students__grades',
    ).order_by('name')
    return {
        'classes': classes, 'checkins': CheckIn.objects.filter(teacher=user).select_related('classroom').order_by('-created_at')[:10],
        'leaves': LeaveRequest.objects.filter(teacher=user).order_by('-date')[:10],
    }


def admin_context(filters):
    return {
        **scout(filters), 'queue': list(pending_issues()),
        'checkins': CheckIn.objects.filter(status=ReviewStatus.PENDING).select_related('teacher', 'classroom').order_by('created_at'),
        'leaves': LeaveRequest.objects.filter(status=ReviewStatus.PENDING).select_related('teacher').order_by('date', 'pk'),
        'records': StudentRecord.objects.select_related('user', 'classroom').order_by('user__username'),
        'teachers': BaseUser.objects.filter(role=Role.TEACHER).order_by('username'),
        'classes': Classroom.objects.order_by('name'),
    }


def finance_context(filters):
    students = list(StudentRecord.objects.select_related('user').filter(user__is_active=True).order_by('user__username'))
    fees = Fee.objects.order_by('student_id', '-due_date', '-pk')
    # dict construction is O(n). Each lookup below is O(1) expected time.
    selected = {}
    for fee in fees:
        previous = selected.setdefault(fee.student_id, fee)
        if previous.paid_on and not fee.paid_on:
            selected[fee.student_id] = fee
    lookup = FeeMap(selected.values())
    context = {'paid': [], 'unpaid': [], 'no_invoice': [], 'lookup_username': filters.get('student', '').strip()}
    for student in students:
        fee = lookup.lookup(student.pk)
        bucket = 'no_invoice' if fee is None else ('paid' if fee.paid_on else 'unpaid')
        context[bucket].append((student, fee))
    by_username = {student.user.username: student.pk for student in students}
    fee = lookup.lookup(by_username.get(context['lookup_username']))
    context['lookup_result'] = ('Paid' if fee.paid_on else 'Unpaid') if fee else 'No invoice found'
    return context


@transaction.atomic
def check_defaulters(actor):
    today = timezone.localdate()
    count = 0
    for fee in Fee.objects.filter(paid_on=None, due_date__lte=today, student__user__is_active=True).select_related('student__user'):
        days = (today - fee.due_date).days
        tier = 2 if days >= 7 else 1
        user = fee.student.user
        message = f'Fee reminder for {user.username}: PKR {fee.amount:,} due {fee.due_date}.'
        issue, created = Issue.objects.get_or_create(
            reference=f'fee-{fee.pk}-tier-{tier}',
            defaults={'author': actor, 'tier': tier, 'text': message},
        )
        if created:
            PortalNotifications().notify([user], message, issue)
            if tier == 2:
                SimulatedWhatsApp().notify([user], message, issue)
            count += 1
    return count


def principal_context(filters):
    grades = Grade.objects.all()
    totals = grades.aggregate(passed=Count('pk', filter=Q(score__gte=50)), failed=Count('pk', filter=Q(score__lt=50)))
    audits = BaseUser.objects.filter(role=Role.TEACHER).annotate(
        graded=Count('classes__students__grades'),
        passed=Count('classes__students__grades', filter=Q(classes__students__grades__score__gte=50)),
        average=Avg('classes__students__grades__score'),
    ).order_by('username')
    month = timezone.localdate().replace(day=1)
    months = [month]
    for _ in range(5):
        months.append((months[-1] - timedelta(days=1)).replace(day=1))
    months.reverse()
    inflow = dict.fromkeys(months, 0)
    outflow = dict.fromkeys(months, 0)
    for date, amount in Fee.objects.filter(paid_on__gte=months[0], paid_on__lte=timezone.localdate()).values_list('paid_on', 'amount'):
        inflow[date.replace(day=1)] += amount
    actor = filters['actor']
    for payroll in TeacherPayroll.objects.filter(month__range=(months[0], months[-1])):
        outflow[payroll.month.replace(day=1)] += payroll.get_salary(actor)
    chart = {'labels': [m.strftime('%b %Y') for m in months], 'inflow': list(inflow.values()),
             'outflow': list(outflow.values()), 'results': [totals['passed'], totals['failed']]}
    return {**scout(filters), **totals, 'audits': audits, 'chart': chart}

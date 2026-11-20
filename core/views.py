import base64
import binascii
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_slug
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import (
    Alert, BaseUser, CheckIn, Classroom, Fee, Grade, Issue, LeaveRequest, ReviewStatus,
    StudentAttendance, StudentRecord, Topic,
)

Role = BaseUser.Role


def home(request):
    return redirect('dashboard')


@login_required
@require_GET
def dashboard(request):
    profile = request.user.dashboard_profile()
    # Polymorphism: the same method dispatches to a different proxy implementation.
    context = profile.get_dashboard_context({**request.GET.dict(), 'actor': profile})
    context['alerts'] = Alert.objects.filter(recipient=request.user).order_by('-created_at')[:8]
    context['role'] = profile.role
    return render(request, f'{profile.role.lower()}.html', context)


def field(post, name, limit):
    value = post.get(name, '').strip()
    if not value or len(value) > limit:
        raise ValidationError(f'{name.replace("_", " ").capitalize()} must contain 1–{limit} characters.')
    return value


def number(post, name):
    try:
        return int(post.get(name, ''))
    except ValueError as error:
        raise ValidationError(f'Enter a whole number for {name}.') from error


def form_date(post):
    try:
        return date.fromisoformat(post.get('date', ''))
    except ValueError as error:
        raise ValidationError('Enter a valid date.') from error


def assigned_class(user, post):
    return get_object_or_404(Classroom, teacher=user, pk=number(post, 'classroom'))


def assigned_student(user, post):
    return get_object_or_404(StudentRecord.objects.select_related('classroom'), classroom__teacher=user, user__is_active=True, pk=number(post, 'student'))


def check_in(user, post):
    classroom = assigned_class(user, post)
    if post.get('qr') != classroom.qr_code or post.get('gps') != 'inside':
        raise ValidationError('Run the classroom QR and GPS simulation successfully before submitting.')
    simulated = post.get('capture') == 'simulated'
    photo_bytes = b''
    if not simulated:
        prefix, _, payload = post.get('snapshot', '').partition(',')
        if prefix != 'data:image/jpeg;base64' or len(payload) > 750_000:
            raise ValidationError('Capture a JPEG snapshot using the camera.')
        try:
            photo_bytes = base64.b64decode(payload, validate=True)
        except binascii.Error as error:
            raise ValidationError('The snapshot is invalid.') from error
        if not photo_bytes.startswith(b'\xff\xd8\xff') or not photo_bytes.endswith(b'\xff\xd9'):
            raise ValidationError('The snapshot is invalid.')
    CheckIn.objects.create(teacher=user, classroom=classroom, photo=photo_bytes, simulated=simulated)
    return 'Check-in submitted as Pending.'


def attendance(user, post):
    student = assigned_student(user, post)
    present = post.get('present')
    if present not in ('yes', 'no'):
        raise ValidationError('Choose Present or Absent.')
    StudentAttendance.objects.update_or_create(
        student=student, date=timezone.localdate(), defaults={'present': present == 'yes'},
    )
    return 'Student attendance saved for today.'


def grade(user, post):
    student = assigned_student(user, post)
    subject = field(post, 'subject', 60)
    existing = Grade.objects.filter(student=student, subject__iexact=subject).first()
    record = existing or Grade(student=student, subject=subject)
    record.set_score(user, number(post, 'score'), lock=post.get('lock') == 'yes')
    return 'Grade saved.'


def topic(user, post):
    item = get_object_or_404(Topic, classroom__teacher=user, pk=number(post, 'id'))
    status = post.get('status')
    if status not in ('Completed', 'Missed'):
        raise ValidationError('Choose a valid syllabus action.')
    services.update_topic(item, status)
    return 'Syllabus updated.'


def add_topic(user, post):
    Topic.objects.create(classroom=assigned_class(user, post), title=field(post, 'title', 100), date=form_date(post))
    return 'Topic added.'


def issue(user, post):
    tier = number(post, 'tier')
    if tier not in Issue.Tier.values:
        raise ValidationError('Choose a valid report tier.')
    services.report_issue(user, tier, field(post, 'message', 250))
    return 'Issue routed.'


def leave(user, post):
    LeaveRequest.objects.create(teacher=user, date=form_date(post), reason=field(post, 'reason', 200))
    return 'Leave request submitted.'


def review(model, post):
    status = post.get('status')
    if status not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
        raise ValidationError('Choose Approve or Reject.')
    changed = model.objects.filter(pk=number(post, 'id'), status=ReviewStatus.PENDING).update(status=status)
    if not changed:
        raise ValidationError('This item has already been reviewed or does not exist.')
    return f'Request {status.lower()}.'


@transaction.atomic
def save_record(user, post):
    role = post.get('role')
    if role not in (Role.TEACHER, Role.STUDENT):
        raise ValidationError('Choose Student or Teacher.')
    pk = post.get('id')
    name = field(post, 'first_name', 150)
    last_name = post.get('last_name', '').strip()
    if len(last_name) > 150:
        raise ValidationError('Last name must contain at most 150 characters.')
    if pk:
        account = get_object_or_404(BaseUser, pk=number(post, 'id'), role=role)
        account.first_name, account.last_name = name, last_name
        account.is_active = post.get('active') == 'yes'
        account.save(update_fields=['first_name', 'last_name', 'is_active'])
    else:
        username = field(post, 'username', 150)
        validate_slug(username)
        password = field(post, 'password', 128)
        account = BaseUser(username=username, role=role, first_name=name, last_name=last_name)
        validate_password(password, account)
        account.set_password(password)
        account.save()
    if role == Role.STUDENT:
        classroom = get_object_or_404(Classroom, pk=number(post, 'classroom'))
        StudentRecord.objects.update_or_create(user=account, defaults={'classroom': classroom})
    return 'Account saved.'


def collect(user, post):
    changed = Fee.objects.filter(pk=number(post, 'id'), paid_on=None).update(paid_on=timezone.localdate())
    if not changed:
        raise ValidationError('This fee has already been collected or does not exist.')
    return 'Payment recorded.'


def resolve(user, post):
    services.resolve_next_issue(number(post, 'id'))
    return 'Oldest issue resolved.'


def cron(user, post):
    return f'{services.check_defaulters(user)} new fee reminders sent.'


ACTIONS = {
    'check-in': (Role.TEACHER, check_in), 'attendance': (Role.TEACHER, attendance),
    'grade': (Role.TEACHER, grade), 'topic': (Role.TEACHER, topic),
    'add-topic': (Role.TEACHER, add_topic), 'issue': (Role.TEACHER, issue),
    'leave': (Role.TEACHER, leave), 'review-checkin': (Role.ADMIN, lambda user, post: review(CheckIn, post)),
    'review-leave': (Role.ADMIN, lambda user, post: review(LeaveRequest, post)),
    'record': (Role.ADMIN, save_record), 'resolve': (Role.ADMIN, resolve),
    'collect': (Role.FINANCE, collect), 'fee-cron': (Role.FINANCE, cron),
}


@login_required
@require_POST
def action(request, action):
    if action not in ACTIONS:
        raise Http404
    role, handler = ACTIONS[action]
    if request.user.role != role:
        raise PermissionDenied
    if request.FILES:
        raise PermissionDenied
    try:
        messages.success(request, handler(request.user, request.POST))
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    except IntegrityError:
        messages.error(request, 'A conflicting record already exists. Refresh and try again.')
    return redirect('dashboard')


@login_required
@require_GET
def photo(request, pk):
    if request.user.role != Role.ADMIN:
        raise PermissionDenied
    entry = get_object_or_404(CheckIn, pk=pk)
    if not entry.photo:
        raise Http404
    response = HttpResponse(bytes(entry.photo), content_type='image/jpeg')
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_GET
def transcript(request, pk):
    if request.user.role != Role.FINANCE:
        raise PermissionDenied
    record = get_object_or_404(StudentRecord.objects.select_related('user'), pk=pk)
    grades = list(record.grades.filter(locked=True).order_by('subject').values_list('subject', 'score'))
    if not grades:
        raise Http404('No finalized grades are available for this student.')
    data = {'student': record.user.get_full_name(), 'id': record.pk, 'grades': grades,
            'issued': timezone.localdate().isoformat()}
    token = signing.dumps(data, salt='school-transcript-v1', compress=True)
    response = render(request, 'transcript.html', {'data': data, 'verification': reverse('verify', args=[token])})
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@require_GET
def verify(request, token):
    # The shared link grants access to its signed transcript payload.
    try:
        data = signing.loads(token, salt='school-transcript-v1')
    except signing.BadSignature as error:
        raise Http404('Invalid transcript signature.') from error
    response = render(request, 'transcript.html', {'data': data, 'verified': True})
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response

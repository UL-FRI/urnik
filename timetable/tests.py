"""
Unit tests for trade request functionality.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from timetable.models import (
    Teacher, Timetable, Activity, ActivitySet, ActivityRealization, 
    Allocation, Classroom, Location, TradeRequest, TradeMatch
)


class TradeRequestModelTests(TestCase):
    """Tests for TradeRequest model."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.user1 = User.objects.create_user(
            username='teacher1',
            password='test123',
            first_name='Teacher',
            last_name='One',
            email='teacher1@test.com'
        )
        self.user2 = User.objects.create_user(
            username='teacher2',
            password='test123',
            first_name='Teacher',
            last_name='Two',
            email='teacher2@test.com'
        )
        
        # Create teachers
        self.teacher1 = Teacher.objects.create(
            user=self.user1,
            code='T1'
        )
        self.teacher2 = Teacher.objects.create(
            user=self.user2,
            code='T2'
        )
        
        # Create timetable
        self.timetable = Timetable.objects.create(
            name='Test Timetable',
            slug='test-timetable'
        )
        
        # Create location and classroom
        self.location = Location.objects.create(name='Main Building')
        self.classroom1 = Classroom.objects.create(
            name='Room 101',
            short_name='R101',
            capacity=30,
            location=self.location
        )
        self.classroom2 = Classroom.objects.create(
            name='Room 102',
            short_name='R102',
            capacity=25,
            location=self.location
        )
        
        # Create activity set
        self.activityset = ActivitySet.objects.create(
            name='Test Activities',
            slug='test-activities'
        )
        
        # Create activities
        self.activity1 = Activity.objects.create(
            name='Math 101',
            short_name='M101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity1.locations.add(self.location)
        
        self.activity2 = Activity.objects.create(
            name='Physics 101',
            short_name='P101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity2.locations.add(self.location)
        
        # Create activity realizations
        self.act_real1 = ActivityRealization.objects.create(
            activity=self.activity1
        )
        self.act_real1.teachers.add(self.teacher1)
        
        self.act_real2 = ActivityRealization.objects.create(
            activity=self.activity2
        )
        self.act_real2.teachers.add(self.teacher2)
        
        # Create allocations
        self.allocation1 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real1,
            classroom=self.classroom1,
            day='MON',
            start='08:00',
        )
        
        self.allocation2 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real2,
            classroom=self.classroom2,
            day='WED',
            start='10:00',
        )
    
    def test_create_trade_request_with_specific_allocation(self):
        """Test creating a trade request with a specific desired allocation."""
        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_allocation=self.allocation2,
            reason='Need to move to Wednesday',
            status='OPEN'
        )
        
        self.assertEqual(trade_request.requesting_teacher, self.teacher1)
        self.assertEqual(trade_request.offered_allocation, self.allocation1)
        self.assertEqual(trade_request.desired_allocation, self.allocation2)
        self.assertEqual(trade_request.status, 'OPEN')
    
    def test_create_trade_request_with_time_preferences(self):
        """Test creating a trade request with time preferences."""
        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_day='TUE',
            desired_start_time='14:00',
            desired_classroom=self.classroom2,
            reason='Prefer Tuesday afternoon',
            status='OPEN'
        )
        
        self.assertEqual(trade_request.desired_day, 'TUE')
        self.assertEqual(trade_request.desired_start_time, '14:00')
        self.assertEqual(trade_request.desired_classroom, self.classroom2)
        self.assertIsNone(trade_request.desired_allocation)
    
    def test_trade_request_status_choices(self):
        """Test that trade request can have different statuses."""
        statuses = ['OPEN', 'MATCHED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED']
        
        for status in statuses:
            trade_request = TradeRequest.objects.create(
                requesting_teacher=self.teacher1,
                offered_allocation=self.allocation1,
                desired_day='TUE',
                status=status
            )
            self.assertEqual(trade_request.status, status)
            trade_request.delete()

    def test_trade_request_expiration(self):
        """Test expiration check for trade requests."""
        expired_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_day='TUE',
            status='OPEN',
            expires_at=timezone.now() - timedelta(days=1)
        )
        active_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_day='WED',
            status='OPEN',
            expires_at=timezone.now() + timedelta(days=1)
        )

        self.assertTrue(expired_request.is_expired())
        self.assertFalse(active_request.is_expired())


class TradeMatchModelTests(TestCase):
    """Tests for TradeMatch matching and approval flow."""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='teacher_match_1',
            password='test123'
        )
        self.user2 = User.objects.create_user(
            username='teacher_match_2',
            password='test123'
        )
        self.teacher1 = Teacher.objects.create(user=self.user1, code='TM1')
        self.teacher2 = Teacher.objects.create(user=self.user2, code='TM2')

        self.timetable = Timetable.objects.create(name='Match Timetable', slug='match-timetable')
        self.location = Location.objects.create(name='Match Building')
        self.classroom1 = Classroom.objects.create(
            name='Match Room 1',
            short_name='MR1',
            capacity=30,
            location=self.location
        )
        self.classroom2 = Classroom.objects.create(
            name='Match Room 2',
            short_name='MR2',
            capacity=30,
            location=self.location
        )

        self.activityset = ActivitySet.objects.create(
            name='Match Activities',
            slug='match-activities'
        )
        self.activity1 = Activity.objects.create(
            name='Match A',
            short_name='MA',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity2 = Activity.objects.create(
            name='Match B',
            short_name='MB',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity1.locations.add(self.location)
        self.activity2.locations.add(self.location)

        self.act_real1 = ActivityRealization.objects.create(activity=self.activity1)
        self.act_real2 = ActivityRealization.objects.create(activity=self.activity2)
        self.act_real1.teachers.add(self.teacher1)
        self.act_real2.teachers.add(self.teacher2)

        self.allocation1 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real1,
            classroom=self.classroom1,
            day='MON',
            start='08:00'
        )
        self.allocation2 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real2,
            classroom=self.classroom2,
            day='WED',
            start='10:00'
        )

    def test_create_match_and_approve(self):
        """Test creating a match and approving swaps allocation times."""
        request_1 = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_allocation=self.allocation2,
            status='OPEN'
        )
        request_2 = TradeRequest.objects.create(
            requesting_teacher=self.teacher2,
            offered_allocation=self.allocation2,
            desired_allocation=self.allocation1,
            status='OPEN'
        )

        trade_match = request_1.create_match(request_2)
        self.assertEqual(request_1.status, 'MATCHED')
        self.assertEqual(request_2.status, 'MATCHED')
        self.assertEqual(trade_match.request_1, request_1)
        self.assertEqual(trade_match.request_2, request_2)

        reviewer = self.teacher1
        trade_match.approve(reviewer, notes='Approved for test')

        self.allocation1.refresh_from_db()
        self.allocation2.refresh_from_db()
        self.assertEqual(self.allocation1.day, 'WED')
        self.assertEqual(self.allocation1.start, '10:00')
        self.assertEqual(self.allocation1.classroom, self.classroom2)
        self.assertEqual(self.allocation2.day, 'MON')
        self.assertEqual(self.allocation2.start, '08:00')
        self.assertEqual(self.allocation2.classroom, self.classroom1)

    def test_reject_match_updates_requests(self):
        """Test rejecting a trade match updates both requests."""
        request_1 = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_allocation=self.allocation2,
            status='OPEN'
        )
        request_2 = TradeRequest.objects.create(
            requesting_teacher=self.teacher2,
            offered_allocation=self.allocation2,
            desired_allocation=self.allocation1,
            status='OPEN'
        )

        trade_match = request_1.create_match(request_2)
        trade_match.reject(self.teacher1, notes='Rejected for test')

        request_1.refresh_from_db()
        request_2.refresh_from_db()
        self.assertEqual(request_1.status, 'REJECTED')
        self.assertEqual(request_2.status, 'REJECTED')
        self.assertIsNone(request_1.matched_with)
        self.assertIsNone(request_2.matched_with)

    def test_execute_trade_swaps_teachers(self):
        """Test executing an approved trade swaps teachers between allocations."""
        request_1 = TradeRequest.objects.create(
            requesting_teacher=self.teacher1,
            offered_allocation=self.allocation1,
            desired_allocation=self.allocation2,
            status='MATCHED'
        )
        request_2 = TradeRequest.objects.create(
            requesting_teacher=self.teacher2,
            offered_allocation=self.allocation2,
            desired_allocation=self.allocation1,
            status='MATCHED'
        )
        trade_match = TradeMatch.objects.create(
            request_1=request_1,
            request_2=request_2,
            status='APPROVED'
        )

        trade_match.execute_trade(self.teacher1)

        teachers_1 = list(self.allocation1.activityRealization.teachers.all())
        teachers_2 = list(self.allocation2.activityRealization.teachers.all())
        self.assertIn(self.teacher2, teachers_1)
        self.assertIn(self.teacher1, teachers_2)


class TradeRequestFormTests(TestCase):
    """Tests for TradeRequestForm validation."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='teacher',
            password='test123',
            first_name='Test',
            last_name='Teacher',
            email='teacher@test.com'
        )
        self.teacher = Teacher.objects.create(
            user=self.user,
            code='T1'
        )
        
        self.timetable = Timetable.objects.create(
            name='Test Timetable',
            slug='test-timetable'
        )
        
        self.location = Location.objects.create(name='Main Building')
        self.classroom = Classroom.objects.create(
            name='Room 101',
            short_name='R101',
            capacity=30,
            location=self.location
        )
        
        self.activityset = ActivitySet.objects.create(
            name='Test Activities',
            slug='test-activities'
        )
        
        self.activity = Activity.objects.create(
            name='Math 101',
            short_name='M101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity.locations.add(self.location)
        
        self.act_real = ActivityRealization.objects.create(
            activity=self.activity
        )
        self.act_real.teachers.add(self.teacher)
        
        self.allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real,
            classroom=self.classroom,
            day='MON',
            start='08:00',
        )
    
    def test_duplicate_active_trade_request_validation(self):
        """Test that creating duplicate active trade requests is prevented."""
        from timetable.forms import TradeRequestForm
        
        # Create first trade request
        TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            status='OPEN'
        )
        
        # Try to create another for the same allocation
        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'WED',
            },
            teacher=self.teacher,
            timetable=self.timetable
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('active trade request', str(form.errors))
    
    def test_teacher_conflict_validation(self):
        """Test that teacher conflicts are detected."""
        from timetable.forms import TradeRequestForm
        
        # Create another allocation for the same teacher at different time
        other_allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real,
            classroom=self.classroom,
            day='TUE',
            start='10:00',
        )
        
        # Try to move to a time when teacher already has a class
        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'TUE',
                'desired_start_time': '10:00',
            },
            teacher=self.teacher,
            timetable=self.timetable
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('Teacher conflict', str(form.errors))
    
    def test_classroom_conflict_validation(self):
        """Test that classroom conflicts are detected."""
        from timetable.forms import TradeRequestForm
        
        # Create another teacher and allocation
        user2 = User.objects.create_user(
            username='teacher2',
            password='test123',
            first_name='Teacher',
            last_name='Two',
            email='teacher2@test.com'
        )
        teacher2 = Teacher.objects.create(
            user=user2,
            code='T2'
        )
        
        activity2 = Activity.objects.create(
            name='Physics 101',
            short_name='P101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        activity2.locations.add(self.location)
        act_real2 = ActivityRealization.objects.create(
            activity=activity2
        )
        act_real2.teachers.add(teacher2)
        
        # Occupy the classroom at TUE 14:00
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=act_real2,
            classroom=self.classroom,
            day='TUE',
            start='14:00',
        )
        
        # Try to move to the same classroom at the same time
        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'TUE',
                'desired_start_time': '14:00',
                'desired_classroom': self.classroom.id,
            },
            teacher=self.teacher,
            timetable=self.timetable
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('Classroom conflict', str(form.errors))

    def test_free_slot_infers_duration_and_marks_free(self):
        """Test that free-slot requests infer duration and mark slot as free."""
        from timetable.forms import TradeRequestForm

        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'TUE',
                'desired_start_time': '14:00',
            },
            teacher=self.teacher,
            timetable=self.timetable
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data.get('_slot_is_free'))
        self.assertEqual(form.cleaned_data.get('desired_duration'), self.allocation.duration)
        self.assertIsNotNone(form.cleaned_data.get('desired_classroom'))

    def test_duplicate_free_slot_request_validation(self):
        """Test that duplicate free-slot requests are rejected."""
        from timetable.forms import TradeRequestForm

        user2 = User.objects.create_user(
            username='teacher_free_2',
            password='test123'
        )
        teacher2 = Teacher.objects.create(user=user2, code='T2')
        activity2 = Activity.objects.create(
            name='Physics 201',
            short_name='P201',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        activity2.locations.add(self.location)
        act_real2 = ActivityRealization.objects.create(activity=activity2)
        act_real2.teachers.add(teacher2)
        allocation2 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=act_real2,
            classroom=self.classroom,
            day='MON',
            start='10:00',
        )

        TradeRequest.objects.create(
            requesting_teacher=teacher2,
            offered_allocation=allocation2,
            desired_day='TUE',
            desired_start_time='14:00',
            desired_duration=self.allocation.duration,
            desired_classroom=self.classroom,
            status='OPEN'
        )

        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'TUE',
                'desired_start_time': '14:00',
                'desired_duration': self.allocation.duration,
                'desired_classroom': self.classroom.id,
            },
            teacher=self.teacher,
            timetable=self.timetable
        )

        self.assertFalse(form.is_valid())
        self.assertIn('already been requested', str(form.errors))

    def test_free_slot_auto_selects_room_with_capacity(self):
        """Test that free-slot selection auto-picks a room meeting capacity constraints."""
        from timetable.forms import TradeRequestForm

        small_room = Classroom.objects.create(
            name='Room 001',
            short_name='R001',
            capacity=10,
            location=self.location
        )
        large_room = Classroom.objects.create(
            name='Room 201',
            short_name='R201',
            capacity=30,
            location=self.location
        )

        self.act_real.intended_size = 40
        self.act_real.save()

        form = TradeRequestForm(
            data={
                'offered_allocation': self.allocation.id,
                'desired_day': 'TUE',
                'desired_start_time': '14:00',
            },
            teacher=self.teacher,
            timetable=self.timetable
        )

        self.assertTrue(form.is_valid(), form.errors)
        selected_room = form.cleaned_data.get('desired_classroom')
        self.assertIsNotNone(selected_room)
        self.assertGreaterEqual(selected_room.capacity, 25)


class TradeRequestViewTests(TestCase):
    """Tests for trade request views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create user and teacher
        self.user = User.objects.create_user(
            username='testteacher',
            password='test123',
            first_name='Test',
            last_name='Teacher',
            email='teacher@test.com'
        )
        self.teacher = Teacher.objects.create(
            user=self.user,
            code='T1'
        )
        
        # Create staff user
        self.staff_user = User.objects.create_user(
            username='admin',
            password='test123',
            first_name='Admin',
            last_name='User',
            email='admin@test.com',
            is_staff=True
        )
        self.staff_teacher = Teacher.objects.create(
            user=self.staff_user,
            code='ADMIN'
        )
        
        self.timetable = Timetable.objects.create(
            name='Test Timetable',
            slug='test-timetable'
        )
        
        self.location = Location.objects.create(name='Main Building')
        self.classroom = Classroom.objects.create(
            name='Room 101',
            short_name='R101',
            capacity=30,
            location=self.location
        )
        
        self.activityset = ActivitySet.objects.create(
            name='Test Activities',
            slug='test-activities'
        )
        
        self.activity = Activity.objects.create(
            name='Math 101',
            short_name='M101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity.locations.add(self.location)
        
        self.act_real = ActivityRealization.objects.create(
            activity=self.activity
        )
        self.act_real.teachers.add(self.teacher)
        
        self.allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real,
            classroom=self.classroom,
            day='MON',
            start='08:00',
        )
    
    def test_create_trade_request_requires_login(self):
        """Test that creating trade request requires authentication."""
        url = reverse('create_trade_request', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
    
    def test_create_trade_request_view_loads(self):
        """Test that trade request creation page loads."""
        self.client.login(username='testteacher', password='test123')
        url = reverse('create_trade_request', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ustvari zahtevo za menjavo')
    
    def test_create_free_slot_trade_request(self):
        """Test creating a trade request for a free slot (goes to PENDING_APPROVAL)."""
        self.client.login(username='testteacher', password='test123')
        url = reverse('create_trade_request', kwargs={'timetable_slug': self.timetable.slug})
        
        response = self.client.post(url, {
            'offered_allocation': self.allocation.id,
            'desired_day': 'TUE',
            'desired_start_time': '14:00',
            'reason': 'Testing free slot',
        })
        
        # Should redirect after success
        self.assertEqual(response.status_code, 302)
        
        # Check trade request was created with PENDING_APPROVAL status
        trade_request = TradeRequest.objects.filter(
            requesting_teacher=self.teacher
        ).first()
        
        self.assertIsNotNone(trade_request)
        self.assertEqual(trade_request.status, 'PENDING_APPROVAL')
        self.assertEqual(trade_request.desired_day, 'TUE')
        self.assertEqual(trade_request.desired_start_time, '14:00')
    
    def test_cancel_trade_request(self):
        """Test canceling a trade request."""
        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            status='OPEN'
        )
        
        self.client.login(username='testteacher', password='test123')
        url = reverse('cancel_trade_request', kwargs={
            'timetable_slug': self.timetable.slug,
            'pk': trade_request.pk
        })
        
        response = self.client.get(url)
        
        # Should redirect after cancellation
        self.assertEqual(response.status_code, 302)
        
        # Check status changed to CANCELLED
        trade_request.refresh_from_db()
        self.assertEqual(trade_request.status, 'CANCELLED')
    
    def test_approval_queue_requires_staff(self):
        """Test that approval queue requires staff permission."""
        # Regular user should be redirected
        self.client.login(username='teacher', password='test123')
        url = reverse('trade_match_queue', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)
        
        # Staff user should see the page
        self.client.login(username='admin', password='test123')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trade Approval Queue')
    
    def test_approve_free_slot_move(self):
        """Test approving a free slot move request."""
        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            desired_start_time='14:00',
            desired_classroom=self.classroom,
            status='PENDING_APPROVAL'
        )
        
        self.client.login(username='admin', password='test123')
        url = reverse('trade_match_queue', kwargs={'timetable_slug': self.timetable.slug})
        
        response = self.client.post(url, {
            'request_id': trade_request.pk,
            'action': 'approve',
        })
        
        # Should redirect after approval
        self.assertEqual(response.status_code, 302)
        
        # Check trade request was approved
        trade_request.refresh_from_db()
        self.assertEqual(trade_request.status, 'APPROVED')
        
        # Check allocation was moved
        self.allocation.refresh_from_db()
        self.assertEqual(self.allocation.day, 'TUE')
        self.assertEqual(self.allocation.start, '14:00')

    def test_reject_trade_request_by_teacher(self):
        """Test rejecting a trade request by the teacher who owns desired allocation."""
        user2 = User.objects.create_user(
            username='otherteacher',
            password='test123'
        )
        teacher2 = Teacher.objects.create(user=user2, code='T2')

        activity2 = Activity.objects.create(
            name='Physics 101',
            short_name='P101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        activity2.locations.add(self.location)
        act_real2 = ActivityRealization.objects.create(activity=activity2)
        act_real2.teachers.add(teacher2)
        allocation2 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=act_real2,
            classroom=self.classroom,
            day='WED',
            start='10:00',
        )

        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_allocation=allocation2,
            status='OPEN'
        )

        self.client.login(username='otherteacher', password='test123')
        url = reverse('reject_trade_request', kwargs={
            'timetable_slug': self.timetable.slug,
            'pk': trade_request.pk
        })
        response = self.client.post(url, {'reason': 'Not available'})

        self.assertEqual(response.status_code, 302)
        trade_request.refresh_from_db()
        self.assertEqual(trade_request.status, 'REJECTED')
        self.assertEqual(trade_request.teacher_rejected_by, teacher2)

    def test_respond_to_trade_request_creates_match(self):
        """Test responding to a trade request creates a match."""
        user2 = User.objects.create_user(
            username='responder',
            password='test123'
        )
        teacher2 = Teacher.objects.create(user=user2, code='T2')

        activity2 = Activity.objects.create(
            name='Chem 101',
            short_name='C101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        activity2.locations.add(self.location)
        act_real2 = ActivityRealization.objects.create(activity=activity2)
        act_real2.teachers.add(teacher2)
        allocation2 = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=act_real2,
            classroom=self.classroom,
            day='WED',
            start='10:00',
        )

        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_allocation=allocation2,
            status='OPEN'
        )

        self.client.login(username='responder', password='test123')
        url = reverse('respond_to_trade_request', kwargs={
            'timetable_slug': self.timetable.slug,
            'pk': trade_request.pk
        })
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        trade_request.refresh_from_db()
        self.assertEqual(trade_request.status, 'MATCHED')
        self.assertTrue(TradeMatch.objects.filter(request_1=trade_request).exists())

    def test_approve_free_slot_denies_when_original_occupied(self):
        """Test approval is denied when the original classroom is occupied."""
        other_activity = Activity.objects.create(
            name='Alt 101',
            short_name='A101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        other_activity.locations.add(self.location)
        other_real = ActivityRealization.objects.create(activity=other_activity)
        other_real.teachers.add(self.teacher)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=other_real,
            classroom=self.classroom,
            day='TUE',
            start='14:00',
        )

        trade_request = TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            desired_start_time='14:00',
            desired_duration=self.allocation.duration,
            status='PENDING_APPROVAL'
        )

        self.client.login(username='admin', password='test123')
        url = reverse('trade_match_queue', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.post(url, {
            'request_id': trade_request.pk,
            'action': 'approve',
        })

        self.assertEqual(response.status_code, 302)
        trade_request.refresh_from_db()
        self.assertEqual(trade_request.status, 'PENDING_APPROVAL')
        self.allocation.refresh_from_db()
        self.assertEqual(self.allocation.day, 'MON')
        self.assertEqual(self.allocation.start, '08:00')


class TradeRequestListViewTests(TestCase):
    """Tests for trade request list views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='teacher',
            password='test123',
            first_name='Test',
            last_name='Teacher',
            email='teacher@test.com'
        )
        self.teacher = Teacher.objects.create(
            user=self.user,
            code='T1'
        )
        
        self.timetable = Timetable.objects.create(
            name='Test Timetable',
            slug='test-timetable'
        )
        
        self.location = Location.objects.create(name='Main Building')
        self.classroom = Classroom.objects.create(
            name='Room 101',
            short_name='R101',
            capacity=30,
            location=self.location
        )
        
        self.activityset = ActivitySet.objects.create(
            name='Test Activities',
            slug='test-activities'
        )
        
        self.activity = Activity.objects.create(
            name='Math 101',
            short_name='M101',
            activityset=self.activityset,
            type='P',
            duration=2
        )
        self.activity.locations.add(self.location)
        
        self.act_real = ActivityRealization.objects.create(
            activity=self.activity
        )
        self.act_real.teachers.add(self.teacher)
        
        self.allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=self.act_real,
            classroom=self.classroom,
            day='MON',
            start='08:00',
        )
    
    def test_trade_request_list_requires_staff(self):
        """Test that trade request list view requires staff."""
        self.client.login(username='teacher', password='test123')
        url = reverse('trade_request_list', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)

    def test_trade_request_list_view_staff(self):
        """Test that trade request list view displays requests for staff."""
        staff_user = User.objects.create_user(
            username='staff',
            password='test123',
            is_staff=True
        )
        Teacher.objects.create(user=staff_user, code='ST')

        TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            status='OPEN'
        )
        
        self.client.login(username='staff', password='test123')
        url = reverse('trade_request_list', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trade Requests')
    
    def test_trade_request_filtering(self):
        """Test filtering trade requests by status."""
        staff_user = User.objects.create_user(
            username='staff_filter',
            password='test123',
            is_staff=True
        )
        Teacher.objects.create(user=staff_user, code='SF')
        self.client.login(username='staff_filter', password='test123')
        TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            status='OPEN'
        )
        
        url = reverse('trade_request_list', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url, {'status': 'OPEN'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['trade_requests']), 1)

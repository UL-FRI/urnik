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
        self.assertContains(response, 'Create Trade Request')
    
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
    
    def test_trade_request_list_view(self):
        """Test that trade request list view displays requests."""
        self.client.login(username='teacher', password='test123')
        TradeRequest.objects.create(
            requesting_teacher=self.teacher,
            offered_allocation=self.allocation,
            desired_day='TUE',
            status='OPEN'
        )
        
        url = reverse('trade_request_list', kwargs={'timetable_slug': self.timetable.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trade Requests')
        self.assertContains(response, str(self.teacher))
    
    def test_trade_request_filtering(self):
        """Test filtering trade requests by status."""
        self.client.login(username='teacher', password='test123')
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

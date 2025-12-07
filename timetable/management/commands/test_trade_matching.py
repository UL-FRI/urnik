"""
Management command to test trade matching functionality.
"""
from django.core.management.base import BaseCommand
from timetable.models import TradeRequest, Teacher, Allocation


class Command(BaseCommand):
    help = 'Test trade request matching functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--teacher-id',
            type=int,
            help='Teacher ID to create test trade request for',
        )
        parser.add_argument(
            '--allocation-id',
            type=int,
            help='Allocation ID to offer for trade',
        )

    def handle(self, *args, **options):
        teacher_id = options.get('teacher_id')
        allocation_id = options.get('allocation_id')
        
        if not teacher_id or not allocation_id:
            self.stdout.write(
                self.style.ERROR(
                    'Please provide both --teacher-id and --allocation-id'
                )
            )
            return
        
        try:
            teacher = Teacher.objects.get(id=teacher_id)
            allocation = Allocation.objects.get(id=allocation_id)
        except (Teacher.DoesNotExist, Allocation.DoesNotExist) as e:
            self.stdout.write(
                self.style.ERROR(f'Object not found: {e}')
            )
            return
        
        self.stdout.write(f'Creating trade request for teacher {teacher}...')
        
        # Create a test trade request
        trade_request = TradeRequest.objects.create(
            requesting_teacher=teacher,
            offered_allocation=allocation,
            reason="Test trade request via management command"
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Created trade request #{trade_request.id}'
            )
        )
        
        # Test finding matches
        self.stdout.write('Finding potential matches...')
        matches = trade_request.find_potential_matches()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Found {len(matches)} potential matches'
            )
        )
        
        for match in matches:
            self.stdout.write(f'  - {match}')
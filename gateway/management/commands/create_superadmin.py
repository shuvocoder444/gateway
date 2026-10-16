import sys
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class Command(BaseCommand):
    help = 'Create or rotate the single Super Admin account without putting its password in shell history.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='superadmin')
        parser.add_argument('--email', default='')
        parser.add_argument('--password-stdin', action='store_true')
        parser.add_argument('--generate-password', action='store_true')
        parser.add_argument('--adopt-existing', action='store_true')

    def handle(self, *args, **options):
        if options['password_stdin'] == options['generate_password']:
            raise CommandError('Choose exactly one of --password-stdin or --generate-password.')

        password = secrets.token_urlsafe(24) if options['generate_password'] else sys.stdin.readline().rstrip('\r\n')
        if len(password) < 12:
            raise CommandError('The Super Admin password must be at least 12 characters.')

        User = get_user_model()
        user = User.objects.filter(username=options['username']).first()
        admins = list(User.objects.filter(is_superuser=True))
        if user and not user.is_superuser and admins:
            raise CommandError('The requested username belongs to a non-admin account.')
        other_admins = [admin for admin in admins if not user or admin.pk != user.pk]
        if other_admins:
            if options['adopt_existing'] and len(admins) == 1 and user is None:
                user = admins[0]
                user.username = options['username']
            else:
                raise CommandError('Another Super Admin already exists. Use --adopt-existing to reset that sole account.')

        if user is None:
            user = User(username=options['username'])
        user.email = options['email']
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Super Admin account {user.username!r} is ready.'))
        if options['generate_password']:
            self.stdout.write(f'Initial password: {password}')

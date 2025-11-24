from django.test import TransactionTestCase, TestCase
from django.conf import settings
import unittest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import Movie, Show, Booking
import threading


class BookingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='alice', password='secret')
        self.user2 = User.objects.create_user(username='bob', password='secret')
        self.movie = Movie.objects.create(title='Test Movie', duration_minutes=120)
        self.show = Show.objects.create(movie=self.movie, screen_name='S1', date_time='2030-01-01T10:00:00Z', total_seats=5)

        # login user to get JWT
        resp = self.client.post('/login', {'username': 'alice', 'password': 'secret'}, format='json')
        assert resp.status_code == status.HTTP_200_OK, resp.content
        self.access = resp.data['access']
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Bearer {self.access}'}

        self.client2 = APIClient()
        resp2 = self.client2.post('/login', {'username': 'bob', 'password': 'secret'}, format='json')
        assert resp2.status_code == status.HTTP_200_OK, resp2.content
        self.access2 = resp2.data['access']
        self.auth_headers2 = {'HTTP_AUTHORIZATION': f'Bearer {self.access2}'}

    def test_book_seat_success(self):
        resp = self.client.post(f'/shows/{self.show.id}/book/', {'seat_number': 1}, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['seat_number'], 1)
        self.assertEqual(resp.data['status'], Booking.STATUS_BOOKED)

    def test_double_booking_prevented(self):
        # First booking succeeds
        resp1 = self.client.post(f'/shows/{self.show.id}/book/', {'seat_number': 1}, format='json', **self.auth_headers)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        # Second booking for same seat should fail
        resp2 = self.client2.post(f'/shows/{self.show.id}/book/', {'seat_number': 1}, format='json', **self.auth_headers2)
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Seat already booked', resp2.data.get('detail', ''))

    def test_out_of_range_seat(self):
        resp = self.client.post(f'/shows/{self.show.id}/book/', {'seat_number': 999}, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_booking_and_rebook(self):
        # Book seat
        resp = self.client.post(f'/shows/{self.show.id}/book/', {'seat_number': 2}, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        booking_id = resp.data['id']
        # Cancel
        resp_cancel = self.client.post(f'/bookings/{booking_id}/cancel/', format='json', **self.auth_headers)
        self.assertEqual(resp_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_cancel.data['status'], Booking.STATUS_CANCELLED)
        # Re-book same seat succeeds
        resp_rebook = self.client2.post(f'/shows/{self.show.id}/book/', {'seat_number': 2}, format='json', **self.auth_headers2)
        self.assertEqual(resp_rebook.status_code, status.HTTP_201_CREATED)

    def test_cannot_cancel_others_booking(self):
        resp = self.client.post(f'/shows/{self.show.id}/book/', {'seat_number': 3}, format='json', **self.auth_headers)
        booking_id = resp.data['id']
        resp_forbidden = self.client2.post(f'/bookings/{booking_id}/cancel/', format='json', **self.auth_headers2)
        self.assertEqual(resp_forbidden.status_code, status.HTTP_403_FORBIDDEN)


@unittest.skipIf(settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3', "SQLite locks across threads; concurrency test skipped.")
class ConcurrencyBookingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.client = APIClient()
        self.client2 = APIClient()
        self.user = User.objects.create_user(username='alice', password='secret')
        self.user2 = User.objects.create_user(username='bob', password='secret')
        self.movie = Movie.objects.create(title='Concurrent Movie', duration_minutes=100)
        self.show = Show.objects.create(movie=self.movie, screen_name='S1', date_time='2030-01-01T10:00:00Z', total_seats=2)
        # tokens
        self.access = self.client.post('/login', {'username': 'alice', 'password': 'secret'}, format='json').data['access']
        self.access2 = self.client2.post('/login', {'username': 'bob', 'password': 'secret'}, format='json').data['access']

    def test_concurrent_booking_same_seat(self):
        results = {}

        def book_with(client, token, key):
            try:
                r = client.post(f'/shows/{self.show.id}/book/', {'seat_number': 1}, format='json', HTTP_AUTHORIZATION=f'Bearer {token}')
                results[key] = r.status_code
            except Exception:
                results[key] = 'error'

        t1 = threading.Thread(target=book_with, args=(self.client, self.access, 'a'))
        t2 = threading.Thread(target=book_with, args=(self.client2, self.access2, 'b'))
        t1.start(); t2.start(); t1.join(); t2.join()

        # One succeeds (201), one fails (400 or 409)
        self.assertIn(results['a'], [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT])
        self.assertIn(results['b'], [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT])
        self.assertNotEqual(results['a'], results['b'])

# Create your tests here.

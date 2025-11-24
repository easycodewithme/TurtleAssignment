from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.db.utils import OperationalError
import time
import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema

from .models import Movie, Show, Booking
from .serializers import (
    SignupSerializer,
    MovieSerializer,
    ShowSerializer,
    BookingSerializer,
    BookSeatSerializer,
)


class SignupView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({'id': user.id, 'username': user.username}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MoviesListView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = MovieSerializer

    def get(self, request):
        movies = Movie.objects.all()
        data = MovieSerializer(movies, many=True).data
        return Response(data)


class MovieShowsListView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ShowSerializer

    def get(self, request, movie_id: int):
        movie = get_object_or_404(Movie, pk=movie_id)
        shows = movie.shows.all().order_by('date_time')
        data = ShowSerializer(shows, many=True).data
        return Response(data)


class BookSeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BookSeatSerializer

    @extend_schema(request=BookSeatSerializer, responses=BookingSerializer)
    def post(self, request, show_id: int):
        show = get_object_or_404(Show, pk=show_id)
        serializer = BookSeatSerializer(data=request.data, context={'show': show})
        serializer.is_valid(raise_exception=True)

        seat_number = serializer.validated_data['seat_number']

        # Concurrency-safe booking with retry logic
        max_retries = 3
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                with transaction.atomic():
                    # Lock the show row to serialize bookings for the same show
                    Show.objects.select_for_update().get(pk=show_id)

                    # Prevent double booking
                    if Booking.objects.filter(show=show, seat_number=seat_number, status=Booking.STATUS_BOOKED).exists():
                        return Response({'detail': 'Seat already booked.'}, status=status.HTTP_400_BAD_REQUEST)

                    # Create booking
                    booking = Booking.objects.create(
                        user=request.user,
                        show=show,
                        seat_number=seat_number,
                        status=Booking.STATUS_BOOKED,
                    )
                    return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)
            except (IntegrityError, OperationalError) as exc:
                # Likely a race on unique constraint; retry a few times with jitter
                last_error = exc
                # Small jittered backoff
                time.sleep(0.05 + random.random() * 0.1)

        # After retries, final check: if seat is booked now, respond clearly
        if Booking.objects.filter(show=show, seat_number=seat_number, status=Booking.STATUS_BOOKED).exists():
            return Response({'detail': 'Seat already booked.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Seat booking conflict. Please retry later.'}, status=status.HTTP_409_CONFLICT)


class CancelBookingView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BookingSerializer

    @extend_schema(responses=BookingSerializer)
    def post(self, request, booking_id: int):
        booking = get_object_or_404(Booking, pk=booking_id)

        # Security: users cannot cancel others' bookings
        if booking.user_id != request.user.id:
            return Response({'detail': 'You cannot cancel another user’s booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.status == Booking.STATUS_CANCELLED:
            return Response({'detail': 'Booking already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        booking.status = Booking.STATUS_CANCELLED
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data, status=status.HTTP_200_OK)


class MyBookingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BookingSerializer

    def get(self, request):
        bookings = Booking.objects.filter(user=request.user).order_by('-created_at')
        data = BookingSerializer(bookings, many=True).data
        return Response(data)

# Create your views here.

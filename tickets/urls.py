from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView
from . import views


urlpatterns = [
    # Auth
    path('signup', views.SignupView.as_view(), name='signup'),
    path('login', TokenObtainPairView.as_view(), name='login'),

    # Movies and shows
    path('movies/', views.MoviesListView.as_view(), name='movies-list'),
    path('movies/<int:movie_id>/shows/', views.MovieShowsListView.as_view(), name='movie-shows'),

    # Booking actions
    path('shows/<int:show_id>/book/', views.BookSeatView.as_view(), name='book-seat'),
    path('bookings/<int:booking_id>/cancel/', views.CancelBookingView.as_view(), name='cancel-booking'),
    path('my-bookings/', views.MyBookingsView.as_view(), name='my-bookings'),
]
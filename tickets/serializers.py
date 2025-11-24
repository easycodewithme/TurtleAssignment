from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Movie, Show, Booking


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['id', 'username', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user


class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = ['id', 'title', 'duration_minutes']


class ShowSerializer(serializers.ModelSerializer):
    movie_id = serializers.IntegerField(source='movie.id', read_only=True)

    class Meta:
        model = Show
        fields = ['id', 'movie_id', 'screen_name', 'date_time', 'total_seats']


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['id', 'show', 'seat_number', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']


class BookSeatSerializer(serializers.Serializer):
    seat_number = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        show = self.context['show']
        seat_number = attrs['seat_number']
        if seat_number > show.total_seats:
            raise serializers.ValidationError('Seat number exceeds total seats for this show.')
        return attrs
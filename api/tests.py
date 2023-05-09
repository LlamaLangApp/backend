from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from api.serializers import UserSerializer


class UserSerializerTest(APITestCase):
    def test_user_serialization(self):
        user = User.objects.create_user(
            username='johndoe',
            email='johndoe@example.com',
            password='password',
            first_name='John',
            last_name='Doe'
        )
        serializer = UserSerializer(instance=user)
        expected_data = {
            'id': user.id,
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
        }
        self.assertEqual(serializer.data, expected_data)

    def test_user_deserialization(self):
        data = {
            'username': 'janedoe',
            'email': 'janedoe@example.com',
            'password': 'password',
            'first_name': 'Jane',
            'last_name': 'Doe',
        }
        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        self.assertEqual(user.username, 'janedoe')
        self.assertEqual(user.email, 'janedoe@example.com')
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Doe')

    def test_user_creation_serializer(self):
        data = {
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password': 'password',
            'first_name': 'John',
            'last_name': 'Doe',
        }
        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        self.assertIsInstance(user, User)
        self.assertEqual(user.username, 'johndoe')
        self.assertEqual(user.email, 'johndoe@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertTrue(user.check_password('password'))

    def test_user_password_update_serializer(self):
        user = User.objects.create_user(
            username='johndoe',
            email='johndoe@example.com',
            password='password',
            first_name='John',
            last_name='Doe'
        )
        data = {
            'password': 'new_password',
        }
        serializer = UserSerializer(instance=user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        user.refresh_from_db()
        self.assertTrue(user.check_password('new_password'))

    def test_user_deletion(self):
        user = User.objects.create_user(
            username='johndoe',
            email='johndoe@example.com',
            password='password',
            first_name='John',
            last_name='Doe'
        )
        serializer = UserSerializer(instance=user)
        user_id = serializer.data['id']
        response = self.client.delete(f'/user/{user_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_create_user(self):
        data = {
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password': 'password',
            'first_name': 'John',
            'last_name': 'Doe',
        }
        response = self.client.post('/api/users/', data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.username, 'johndoe')
        self.assertEqual(user.email, 'johndoe@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertTrue(user.check_password('password'))


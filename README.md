# LlamaLang backend

## Set-up

### Installation

1. Clone the repository
2. Create venv in root folder

```commandline
python -m venv venv
```

3. Activate venv:

   For macOS:

   ```commandline
   source venv/bin/activate
   ```

   For Windows:

   ```commandline
    venv\Scripts\activate
   ```

4. Install dependencies specified in requirements.txt

```commandline
pip install -r requirements.txt
```

If it doesn't work also try:

```commandline
python manage.py runserver 0.0.0.0:8000
```

5. Run the server

```commandline
python manage.py runserver
```

### Development Set-up

1. Run migration to generate db schema:

```commandline
python manage.py migrate
```

2. Create user that you will use for manual tests purpose

```commandline
python manage.py create_user <username> <passsword>
```

3. Initiate test data in database:

```commandline
python manage.py init_word_sets
```

4. Login via `/auth/token/login/` endpoint with the credentials of previously created user. On success, the endpoint will return token needed to use API.
   When making requests to API, put received token in Authentication header:

```
Authentication: token <your_token>
```

5. You are ready to develop!

### Regenerate open-api schema

Run

```commandline
python .\manage.py generateschema --format=openapi-json --file openapi.json
```

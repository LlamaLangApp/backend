# LlamaLang backend

## Running

1. Clone the repository
2. Run `docker compose up`

### Dev setup

1. Create venv in root folder

```commandline
python -m venv venv
```

2. Activate venv:

   For macOS:

   ```commandline
   source venv/bin/activate
   ```

   For Windows:

   ```commandline
    venv\Scripts\activate
   ```

3. Install dependencies specified in requirements.txt

```commandline
pip install -r requirements.txt
```

4. Run the server

```commandline
python manage.py runserver
```

If it doesn't work also try:

```commandline
python manage.py runserver 0.0.0.0:8000
```

## Development Notes

### Testing

Login via `/auth/token/login/` endpoint with the credentials of previously created user. On success, the endpoint will return token needed to use API.
When making requests to API, put received token in Authentication header:

```
Authentication: token <your_token>
```

### Regenerate open-api schema

Run

```commandline
python .\manage.py generateschema --format=openapi-json --file openapi.json
```

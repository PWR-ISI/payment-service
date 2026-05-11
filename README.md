# Payment Service - Setup Guide

Kompletny przewodnik do uruchomienia Payment Service z integracją PayU i AWS SQS.

## 📋 Wymagania

- Python 3.11+
- Django 4.2+
- PostgreSQL 12+ (lub SQLite dla dev)
- AWS Account (dla SQS)
- PayU Sandbox Account (https://www.getpayu.com/)
- git-secrets (do ochrony credentials)

## 🚀 Setup krok po kroku

### Krok 1: Virtual Environment

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Krok 2: Instalacja dependencji

```bash
pip install -r requirements.txt
```

### Krok 3: Konfiguracja zmiennych środowiskowych

```bash
# Skopiuj template
cp .env.example .env

# Edytuj .env z właściwymi wartościami
```

**Gdzie pobrać wartości:**

#### PayU Sandbox Credentials
1. Wejdź na https://www.getpayu.com/
2. Zaloguj się na swoje konto sandbox
3. Przejdź do: Ustawienia → Dane Handlowca → Identyfikatory
4. Skopiuj:
   - `PAYU_MERCHANT_ID` (Merchant ID)
   - `PAYU_API_KEY` (API Key / klucz)
   - `PAYU_OAUTH_CLIENT_ID` (OAuth - Client ID)
   - `PAYU_OAUTH_CLIENT_SECRET` (OAuth - Client Secret)

#### AWS Credentials
1. Wejdź na AWS Console (https://console.aws.amazon.com/)
2. IAM → Users → Utwórz nowego usera
3. Permissions: SQS FullAccess (dla dev) lub custom policy
4. Security Credentials → Create Access Key
5. Skopiuj `AWS_ACCESS_KEY_ID` i `AWS_SECRET_ACCESS_KEY`

#### AWS SQS Queues
1. SQS → Create Queue
2. Utwórz dwie kolejki:
   - `payment-success` (Standard)
   - `payment-failed` (Standard)
3. Skopiuj URLs do `.env`

**Przykładowe .env:**
```dotenv
DJANGO_SECRET_KEY=django-insecure-your-secret-key-here-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,example.com

PAYU_MERCHANT_ID=1234567
PAYU_API_KEY=abc123xyz789
PAYU_OAUTH_CLIENT_ID=client-id-from-payu
PAYU_OAUTH_CLIENT_SECRET=secret-from-payu
PAYU_SANDBOX_MODE=true

AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_SQS_PAYMENT_SUCCESS_QUEUE_URL=https://sqs.eu-central-1.amazonaws.com/123456789012/payment-success
AWS_SQS_PAYMENT_FAILED_QUEUE_URL=https://sqs.eu-central-1.amazonaws.com/123456789012/payment-failed

BASE_URL=http://localhost:8000
LOG_LEVEL=INFO
```

### Krok 4: Baza danych

```bash
# Migracje
python manage.py makemigrations
python manage.py migrate

# Superuser (do Django Admin)
python manage.py createsuperuser
# Username: admin
# Email: admin@example.com
# Password: admin123
```

### Krok 5: Uruchomienie serwera

```bash
python manage.py runserver

# Server: http://localhost:8000
# API: http://localhost:8000/api/payments/
# Admin: http://localhost:8000/admin/
```

## 🔐 git-secrets Setup (ochrona credentials)

### Instalacja

```bash
# Windows (Chocolatey)
choco install git-secrets

# Linux (Ubuntu/Debian)
sudo apt-get install -y git-secrets

# Mac (Homebrew)
brew install git-secrets
```

### Konfiguracja w projekcie

```bash
# W katalogu payment-service

# Inicjalizacja
git secrets --install

# Dodanie AWS patterns
git secrets --register-aws

# Dodanie custom patterns dla PayU
git secrets --add 'PAYU_MERCHANT_ID\s*=\s*[0-9]+'
git secrets --add 'PAYU_API_KEY\s*='
git secrets --add 'PAYU_OAUTH_CLIENT_SECRET\s*='

# Sprawdzenie current setup
git secrets --list
```

### Test setup'u

```bash
# Spróbuj zacommitować wrażliwe dane (powinno być zablokowane)
echo "PAYU_API_KEY=secret123" >> .env-test
git add .env-test
git commit -m "test"
# ❌ Error: git-secrets detected potential AWS credentials

# Cleanup
git reset HEAD .env-test
rm .env-test
```

## 📚 API Endpoints

### Create Order (Tworzenie zamówienia)
```bash
POST /api/payments/orders/

{
  "appointment_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "660e8400-e29b-41d4-a716-446655440001",
  "amount": "100.00",
  "currency": "PLN",
  "description": "Wizyta u kardiologa"
}

# Response 201
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "appointment_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.00",
  "status": "RESERVED",
  "payment": {
    "id": "...",
    "payu_order_id": "435726487",
    "payu_status": "PENDING"
  }
}
```

### Get Order
```bash
GET /api/payments/orders/770e8400-e29b-41d4-a716-446655440002/
```

### List Orders
```bash
GET /api/payments/orders/?patient_id=660e8400-e29b-41d4-a716-446655440001
```

### Order Audit Trail
```bash
GET /api/payments/orders/770e8400-e29b-41d4-a716-446655440002/audit_logs/

# Response: Historia wszystkich zmian
[
  {
    "id": "...",
    "action": "ORDER_CREATED",
    "actor_type": "SYSTEM",
    "details": {...},
    "created_at": "2026-05-10T12:00:00Z"
  }
]
```

### Payment Webhook (z PayU)
```bash
POST /api/payments/webhook

Headers:
  OpenPayU-Signature: [computed MD5 signature]

Body:
{
  "order": {
    "orderId": "435726487",
    "orderStatus": "COMPLETED",
    "totalAmount": 10000
  },
  "localMerchantId": "1234567"
}

# Response 200
{"status": "OK"}
```

### Health Check
```bash
GET /api/payments/health

# Response
{"status": "OK", "service": "payment-service"}
```

## 🧪 Testing API

### Postman Collection

Importuj poniższy JSON do Postman'a lub używaj poniższych curl'ów:

```bash
# 1. Create Order
curl -X POST http://localhost:8000/api/payments/orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "appointment_id": "550e8400-e29b-41d4-a716-446655440000",
    "patient_id": "660e8400-e29b-41d4-a716-446655440001",
    "amount": "100.00",
    "description": "Test wizyta"
  }'

# 2. Get Orders
curl http://localhost:8000/api/payments/orders/

# 3. Health Check
curl http://localhost:8000/api/payments/health
```

## 📖 Dokumentacja

- **Models**: `payments/models.py`
- **Services**: `payments/services.py` (PayU, SQS, Order logic)
- **Views/API**: `payments/views.py`
- **Settings**: `payment/settings.py`

## 🔍 Logi

```bash
# Console logs w real-time
python manage.py runserver

# File logs (rotuje automatycznie)
tail -f logs/payment-service.log

# Loglevel zmieniaj przez .env
LOG_LEVEL=DEBUG  # Więcej detali
LOG_LEVEL=INFO   # Standardowy
LOG_LEVEL=ERROR  # Tylko błędy
```

## 🐛 Troubleshooting

### ImportError: No module named 'dotenv'
```bash
pip install python-dotenv
```

### PayU Authentication Failed
- ✓ Sprawdź PAYU_OAUTH_CLIENT_ID i PAYU_OAUTH_CLIENT_SECRET
- ✓ Sprawdź PAYU_SANDBOX_MODE=true
- ✓ Sprawdź internet connection

### SQS Connection Error
- ✓ Sprawdź AWS_ACCESS_KEY_ID i AWS_SECRET_ACCESS_KEY
- ✓ Sprawdź AWS_REGION
- ✓ Sprawdź QUEUE URLs

### Webhook not received
- ✓ Webhook wymaga publicznego adresu (PayU musi się dostać do twojego servera)
- ✓ W dev: użyj ngrok do tunelowania: `ngrok http 8000`
- ✓ Update BASE_URL w .env na ngrok URL

## 🚀 Deployment

### Production Checklist

- [ ] `DEBUG = False`
- [ ] `ALLOWED_HOSTS` skonfigurowany
- [ ] `SECRET_KEY` zmieniony
- [ ] PostgreSQL zamiast SQLite
- [ ] `PAYU_SANDBOX_MODE = false`
- [ ] git-secrets zainstalany i skonfigurowany
- [ ] HTTPS/TLS certyfikat
- [ ] Backup bazy danych
- [ ] Sentry do error tracking

### Docker

```bash
# Build
docker build -t payment-service:latest .

# Run
docker run -p 8000:8000 --env-file .env payment-service:latest
```

## 📞 Contacts

- **PayU Support**: https://www.getpayu.com/en/support
- **AWS SQS Docs**: https://docs.aws.amazon.com/sqs/
- **Django Docs**: https://docs.djangoproject.com/


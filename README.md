# Newsletter to LinkedIn Post Automation

Automated backend system that converts newsletter emails into LinkedIn posts.

## Features

- Gmail Pub/Sub webhook integration
- AI-powered content transformation using OpenAI
- Automatic logging to Google Sheets
- Telegram notifications
- Comprehensive error handling and retry logic
- Email deduplication
- Sender allowlist validation

## Setup

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.template .env
# Edit .env with your actual credentials
```

### 3. Google Cloud Setup

1. Create a service account in Google Cloud Console
2. Enable Gmail API and Google Sheets API
3. Download service account credentials JSON
4. Save as `config/service-account-credentials.json`
5. Share your Google Sheet with the service account email

### 4. Run the Application

```bash
python src/main.py
```

## Project Structure

```
.
├── config/                 # Configuration files
├── logs/                   # Application logs
│   └── fallback/          # Fallback logs for failed operations
├── src/
│   ├── api/               # Flask endpoints
│   ├── config/            # App configuration
│   ├── integrations/      # External API clients
│   ├── services/          # Business logic
│   └── utils/             # Helper utilities
├── tests/                 # Test files
├── .env.template          # Environment variable template
├── requirements.txt       # Python dependencies
└── README.md
```

## Testing

```bash
pytest tests/ -v --cov=src
```

## Environment Variables

See `.env.template` for all required configuration variables.

## License

MIT

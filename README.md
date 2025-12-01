# Paper Slack Bot 📚🤖

A Slack-focused scientific paper discovery bot inspired by [PaperBee](https://github.com/theislab/paperbee/) but with enhanced features focusing on **Slack integration**, **better searching capability**, and **journal name filtering**.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

### 📰 Paper Fetching
- Fetch papers from multiple sources:
  - **PubMed** (via NCBI E-utilities API)
  - **bioRxiv** (via bioRxiv API)
  - **arXiv** (via arXiv API)
- Configurable date ranges (e.g., last 24h, last 7 days)
- Automatic deduplication using DOI

### 🔍 Enhanced Search (Better than PaperBee)
- **Keyword-based search** with boolean operators (AND, OR, NOT)
- **Semantic search** using sentence embeddings for finding conceptually related papers
- **Advanced filtering**:
  - By author names
  - By date range
  - By keywords in title/abstract
  - Exclude specific terms
- **Search history** stored in local SQLite database

### 📚 Journal Name Filtering (NEW - Not in PaperBee)
- Filter papers by specific journal names (include/exclude lists)
- Support journal tiers/categories:
  - 🏆 **Tier 1**: Nature, Science, Cell, NEJM, Lancet
  - ⭐ **Tier 2**: Nature Methods, Nature Communications, PNAS, eLife
  - 🤖 **ML-focused**: NeurIPS, ICML, Nature Machine Intelligence
  - 📝 **Preprints**: bioRxiv, arXiv, medRxiv
- Journal name prominently displayed in Slack messages

### 🤖 LLM-Based Filtering
- Use OpenAI API (GPT-4o-mini) for intelligent paper relevance filtering
- Support for local Ollama models as alternative
- Configurable filtering prompts describing research interests
- Returns relevance scores and brief explanations

### 💬 Slack Integration (Primary Focus)
- Rich message formatting with paper details
- Interactive action buttons (Save, Share, Dismiss)
- **Slash Commands**:
  - `/papersearch <query>` - Search papers interactively
  - `/papersubscribe <keywords>` - Subscribe to topics
  - `/paperjournals` - List/configure preferred journals
  - `/papersettings` - View/update bot settings
- **Scheduled posting** - Daily digest to configured channel

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Ambuj0507/paper-slack-bot.git
cd paper-slack-bot

# Install with Poetry (recommended)
poetry install

# Or with pip
pip install -e .
```

### Configuration

1. Copy the example configuration:
```bash
cp config.example.yml config.yml
```

2. Set up environment variables:
```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"
export OPENAI_API_KEY="sk-your-openai-key"
export NCBI_API_KEY="your-ncbi-key"  # Optional but recommended
```

3. Edit `config.yml` with your settings:
```yaml
slack:
  bot_token: "${SLACK_BOT_TOKEN}"
  app_token: "${SLACK_APP_TOKEN}"
  channel_id: "C0123456789"  # Your channel ID

search:
  keywords:
    - "machine learning"
    - "single-cell RNA"
  databases:
    - pubmed
    - biorxiv
    - arxiv
  days_back: 1

journals:
  tiers:
    - tier1
    - tier2
  show_preprints: true
```

### Run the Bot

```bash
# Start the Slack bot server
paper-slack-bot serve --config config.yml

# Or post papers once
paper-slack-bot post --config config.yml --days 1

# Search papers (console output)
paper-slack-bot search "machine learning biology" --config config.yml
```

## 📖 Detailed Setup

### Creating a Slack App

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click "Create New App" > "From a manifest"
3. Select your workspace
4. Copy the contents of `manifest.json` from this repository
5. Create the app

After creation:
1. Go to "OAuth & Permissions" and install the app to your workspace
2. Copy the "Bot User OAuth Token" (starts with `xoxb-`)
3. Go to "Basic Information" and generate an "App-Level Token" with `connections:write` scope
4. Copy the App-Level Token (starts with `xapp-`)

### Getting API Keys

#### NCBI API Key (recommended for PubMed)
1. Register at [NCBI](https://www.ncbi.nlm.nih.gov/account/)
2. Go to Settings > API Key Management
3. Generate a new API key

#### OpenAI API Key (for LLM filtering)
1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Create a new API key

### Using Ollama (Local LLM Alternative)

Instead of OpenAI, you can use local Ollama models:

```yaml
llm:
  provider: "ollama"
  model: "llama2"
  base_url: "http://localhost:11434/v1"
```

## 🔧 Configuration Options

### Full config.yml Reference

```yaml
# Slack Configuration
slack:
  bot_token: "${SLACK_BOT_TOKEN}"    # Required: Bot OAuth token
  app_token: "${SLACK_APP_TOKEN}"    # Required: App-level token
  channel_id: "C0123456789"          # Required: Channel to post to

# API Keys
ncbi_api_key: "${NCBI_API_KEY}"      # Optional: NCBI/PubMed API key
openai_api_key: "${OPENAI_API_KEY}"  # Optional: OpenAI API key

# Search Configuration
search:
  keywords:                          # Keywords to search for
    - "machine learning"
    - "deep learning"
  databases:                         # Sources to search
    - pubmed
    - biorxiv
    - arxiv
  days_back: 1                       # Days to look back

# Journal Filtering
journals:
  include:                           # Whitelist specific journals
    - "Nature"
    - "Science"
  exclude: []                        # Blacklist specific journals
  tiers:                             # Include journal tiers
    - tier1                          # Nature, Science, Cell, etc.
    - tier2                          # Nature Methods, PNAS, etc.
    - ml                             # NeurIPS, ICML, etc.
  show_preprints: true               # Include bioRxiv/arXiv

# LLM Configuration
llm:
  provider: "openai"                 # "openai" or "ollama"
  model: "gpt-4o-mini"               # Model name
  base_url: null                     # Custom API endpoint
  filtering_prompt: |                # Custom prompt
    Rate papers for machine learning in biology.

# Schedule Configuration
schedule:
  enabled: true                      # Enable scheduled posting
  time: "09:00"                      # Post time (24h format)
  timezone: "UTC"                    # Timezone

# Storage Configuration
storage:
  database_path: "papers.db"         # SQLite database path
  cache_days: 30                     # Days to cache papers
```

## 💻 CLI Commands

### Post Papers to Slack
```bash
paper-slack-bot post --config config.yml --days 1

# Dry run (print to console without posting)
paper-slack-bot post --config config.yml --dry-run
```

### Search Papers
```bash
# Basic search
paper-slack-bot search "machine learning" --config config.yml

# Search specific sources
paper-slack-bot search "genomics" --source pubmed --source biorxiv

# Limit results
paper-slack-bot search "protein structure" --limit 10
```

### Run Bot Server
```bash
paper-slack-bot serve --config config.yml
```

### Test Configuration
```bash
paper-slack-bot test-config --config config.yml
```

### Clean Up Old Papers
```bash
paper-slack-bot cleanup --config config.yml --days 30
```

## 📱 Slack Commands

Once the bot is running, use these slash commands in Slack:

### `/papersearch <query>`
Search for papers interactively.
```
/papersearch machine learning genomics
/papersearch "single cell" AND RNA NOT clinical
```

### `/papersubscribe <keywords>`
Subscribe to topics for daily updates.
```
/papersubscribe machine learning, deep learning
/papersubscribe
```

### `/paperjournals [tier]`
View journal configurations.
```
/paperjournals
/paperjournals tier1
/paperjournals ml
```

### `/papersettings`
View current bot settings.

## ⏰ GitHub Actions Setup

The repository includes a GitHub Actions workflow for automated daily posting:

1. Go to your repository Settings > Secrets and variables > Actions
2. Add these secrets:
   - `SLACK_BOT_TOKEN`
   - `SLACK_APP_TOKEN`
   - `SLACK_CHANNEL_ID`
   - `OPENAI_API_KEY`
   - `NCBI_API_KEY`

3. The workflow runs daily at 9:00 AM UTC. To trigger manually:
   - Go to Actions > Daily Paper Post > Run workflow

## 🧪 Development

### Running Tests
```bash
# Install dev dependencies
poetry install --with dev

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=paper_slack_bot
```

### Code Style
```bash
# Format code
poetry run black src tests
poetry run isort src tests

# Lint
poetry run flake8 src tests

# Type checking
poetry run mypy src
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`poetry run pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by [PaperBee](https://github.com/theislab/paperbee/)
- Uses [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/) for PubMed access
- Uses [bioRxiv API](https://api.biorxiv.org/) for preprints
- Uses [arXiv API](https://arxiv.org/help/api/) for ML papers

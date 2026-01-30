# Last Man Standing (LMS)

A web-based football prediction game where players pick one team to win each gameweek.

## How it works
- **One Pick per Week**: Each player picks one team to win their match.
- **Win to Stay In**: If your team wins, you advance to the next week.
- **Lose/Draw and You're Out**: If your team loses or draws, you are eliminated.
- **No Repeats**: You cannot pick the same team more than once in a single competition.
- **Last Man Standing**: The last remaining player wins the pot.

## Tech Stack
- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) with [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Database**: SQLite
- **Frontend**: Vanilla JavaScript, HTML5, and CSS
- **External API**: [football-data.org](https://www.football-data.org/) for Premier League fixtures and results

## Prerequisites
- Python 3.9+
- An API Key from [football-data.org](https://www.football-data.org/) (Free tier available)

## Running with Python (locally)

1. **Clone the repository**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Set your API Key**:
   ```bash
   export FOOTBALL_DATA_API_KEY="your_api_key_here"
   ```
4. **Initialize the Admin user**:
   ```bash
   python init_admin.py
   ```
   *Note: This creates a default admin with PIN `99999`.*
5. **Start the server**:
   ```bash
   uvicorn main:app --reload
   ```
6. **Access the application**:
   - Player Interface: `http://localhost:8000/player.html`
   - Admin Interface: `http://localhost:8000/admin.html` (PIN: `99999`)

## Running with Docker

1. **Build the image**:
   ```bash
   docker build -t lms-game .
   ```
2. **Run the container**:
   ```bash
   docker run -p 8000:8000 -e FOOTBALL_DATA_API_KEY="your_api_key_here" lms-game
   ```

## Admin Features
- **Sync Fixtures**: Fetch the latest Premier League fixtures and update gameweek deadlines.
- **Manage Users**: Create and delete players.
- **Process Results**: Automatically calculate who is through and who is eliminated based on match results.
- **Manual Overrides**: Admins can set picks for players if needed.

## Database Schema
The application uses SQLite with the following main tables:
- `user`: Stores player details, PINs, and active status.
- `gameweek`: Tracks deadlines and processing status.
- `fixture`: Stores match information and results.
- `pick`: Records player team selections.

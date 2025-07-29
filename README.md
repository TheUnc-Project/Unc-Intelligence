# WorthBucks API

This is the WorthBucks client API

## Requirements

- Python 3.7+
- FastAPI
- Uvicorn
- python-dotenv

## Installation

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up the environment variables:**

   Create a `.env` file in the root directory and add the necessary environment variables:

   ```text
   SECRET_KEY=your_secret_key_here
   DATABASE_URL=your_database_url_here
   NEW_NAME=your_new_name_here
   ```

## Running the Application

1. **Start the application:**

   Use the provided start script:

   ```bash
   ./start_app.sh
   ```

   Or run Uvicorn directly:

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Access the application:**

   Open your browser and go to `http://localhost:8000` to access the application. 
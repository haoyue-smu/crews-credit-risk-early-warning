🏦 UBS Credit Assessment Agent
Setup Guide

Ensure the following tools are installed:

Tool	Version
Python	3.11 or 3.12
Git	Latest
VS Code	Recommended

Check Python version:

python --version

📥 2. Clone the Repository

Clone the project and enter the directory.

git clone <repo-url>
cd ubs_credit_assessment_smu

🧪 3. Create a Virtual Environment

From the project root:

python -m venv .venv

⚡ 4. Activate the Virtual Environment
Windows
.venv\Scripts\activate
Mac / Linux
source .venv/bin/activate

Your terminal should now show:

(.venv)

📦 5. Install Dependencies

Install the required packages:

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

🔐 6. Environment Variables

Create a .env file in the project root.

Example:

GEMINI_API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/credit_agent

🚀 7. Run the Backend

From the project root run:

python -m uvicorn backend.main:app --reload

The backend will start at:

http://127.0.0.1:8000
Test the API

Open:

http://127.0.0.1:8000/docs

You should see the FastAPI interactive API documentation.

🖥 8. Run the Frontend

Open a new terminal, activate the virtual environment again, then run:

streamlit run app/main.py

The Streamlit interface will open at:

http://localhost:8501

🧪 9. Test the System

Inside the Streamlit interface:

1️⃣ Enter an Entity Name
2️⃣ Select Entity Type
3️⃣ Enter Location
4️⃣ Click Assess

The frontend will call the backend API and display the returned JSON response.

🧑‍💻 10. Development Workflow

Always run commands from the project root directory.

Start Backend
python -m uvicorn backend.main:app --reload
Start Frontend
streamlit run app/main.py
⚠️ 11. Common Issues
ModuleNotFoundError

Make sure:

The virtual environment is activated

Dependencies are installed

Commands are run from the project root

Install dependencies again if needed:

python -m pip install -r requirements.txt
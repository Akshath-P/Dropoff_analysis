# Step 1: Create venv
python -m venv .venv

. .\.venv\Scripts\activate

pip install pip-tools

python -m piptools compile requirements.in --verbose

pip install -r requirements.txt

uvicorn bi_agents.main:app --app-dir src
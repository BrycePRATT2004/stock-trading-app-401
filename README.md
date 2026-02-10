#STOCK TRADING APP

##STACK
Front End : HTML / CSS / JavaSCRIPT 
Back End : Python + Flask

## PROJECT STRUCTURE
Stock-Trading-App

app.py  
templates/ (HTML files)  
static/css (styles)  
static/js (frontend JS)  
data/users.json (fake database)  
## Initial Setup (already done on Bryce’s machine)

1. Created virtual environment:

python3 -m venv venv

2. Activated it:

source venv/bin/activate

3. Installed Flask:

pip install flask

4. Saved dependencies:

pip freeze > requirements.txt

---

## Teammate Setup Instructions

After downloading/cloning the project:

1. Open folder in VS Code

2. Create virtual environment:

python3 -m venv venv

3. Activate it:

source venv/bin/activate

4. Install dependencies:

pip install -r requirements.txt

---

## Important

Every time you reopen the project, run:

source venv/bin/activate

or Flask will not work.

---

## File Purpose

app.py = Flask backend  
templates/ = HTML pages  
static/css = styling  
static/js = browser JavaScript  
data/users.json = fake database  
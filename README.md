# Gym Membership & Fitness Session Management System

DBMS project: a relational design for a gym (14 tables in 3NF with keys, CHECK constraints and triggers) and a live demo that writes into MongoDB.

## Contents

| Path | What it is |
|---|---|
| `Gym DBMS Live Demo.html` | Interactive demo: insert members, subscriptions, bookings and check-ins, watch each constraint run on the ER model, and do CRUD on any table (tab 5) |
| `database/gym_server.py` | Local server that connects the demo to MongoDB (`gym_db`) and enforces the same rules |
| `*.pptx`, `*.docx`, `*.pdf` | Review decks and project report |

## Run the demo with MongoDB

Requires Python 3 and a local MongoDB server on `mongodb://127.0.0.1:27017`.

```bash
pip install pymongo
python database/gym_server.py
```

The server creates the `gym_db` database (collections, validators, unique indexes and sample data) on first start and opens the demo at http://127.0.0.1:8770/. Every committed change in the demo is saved to MongoDB; view it in MongoDB Compass.

Opening the HTML file without the server still works; the demo then runs its in-browser engine and nothing is saved.

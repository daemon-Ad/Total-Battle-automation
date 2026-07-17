# Total Battle Chest Tracker & Analytics Dashboard

An automated system designed to track clan chest contributions, analyze weekly targets, and manage player progress through a centralized web dashboard.

## Overview

Managing clan chest contributions manually can be tedious. This project automates the extraction and tallying of chest data, storing it securely in a PostgreSQL database, and presenting the data through a FastAPI-powered analytics dashboard. 

The system tracks overall clan progress against weekly goals, identifies members who are falling behind or excelling, and provides trends on chest collection over time.

## Key Features

- **Automated Data Processing**: Captures and processes chest extraction logs, calculating point values dynamically based on chest rarity (Common, Rare, Epic) and source (Crypts, Events, Monsters, etc.).
- **Real-Time Analytics Dashboard**: A single-page application (SPA) offering detailed insights into weekly targets, active members, and chest distribution.
- **Player Management**: Add, update, or remove clan members, and track their individual contribution scores.
- **Weekly Goal Configuration**: Set global weekly point targets that automatically sync across the dashboard to calculate member adherence.
- **Secure Access**: HTTP Basic Authentication restricts dashboard access strictly to authorized users.

## Screenshots

### Main Dashboard & Analytics
![Homepage](./images/readme-images/homepage.png)
*Provides a high-level summary of the clan's weekly progress, showing exactly who is on track and who needs attention.*

### Chest Frequency Trends
![Chest Frequency](./images/readme-images/chest-freq.png)
*Tracks the volume and score of collected chests over time, grouped by daily or hourly intervals.*

### Goal Setting & Configuration
![Goal Setting](./images/readme-images/goal-setting.png)
*Easily update the weekly automation parameters to adjust clan requirements.*

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- PostgreSQL database
- Tesseract OCR (if running the extraction scripts)

### 2. Environment Configuration
Create a `.env` file in the root directory (or next to your database scripts) with the following credentials:
```env
DB_HOST=localhost
DB_NAME=tb_automation
DB_USER=tb_user
DB_PASS=your_password
DB_PORT=5432
```

### 3. Database Initialization
Ensure your database is running. The `db.py` module will automatically initialize the required schema (`users`, `players`, `chest_logs`) upon connection and seed the default user accounts.

### 4. Running the Dashboard
Start the FastAPI server:
```bash
python app.py
```

## Usage

1. **Login**: Access the dashboard using one of the preset user accounts.
2. **Dashboard Review**: The Home view will immediately display the current week's progress based on game reset times (counting from Monday 00:00 UTC).
3. **Settings**: Navigate to the **Chest settings** tab to define the current week's point requirement. All progress bars and "Needs Attention" lists will automatically recalibrate.
4. **Data Intake**: As the Python extraction scripts process game logs, the database will populate automatically, and the dashboard will reflect the new chest scores in real-time.

 # 🚀 QueueLess

> A Smart Digital Queue and Appointment Management System that helps businesses manage customer appointments, waiting lists, and queues while providing customers with a convenient booking and queue-tracking experience.

## 📌 About the Project   

QueueLess is a web-based queue and appointment management platform designed to simplify customer flow and reduce waiting time.

The platform provides separate portals for administrators and customers. Businesses can manage their services, appointments, customers, and digital queues, while customers can book appointments and track their appointment status.

## ✨ Features

### 🏢 Business Management
- Business dashboard and overview.
- Business selection and management.
- Service creation and management.
- Business appointment management.

### 👥 Customer Portal
- Customer registration and login.
- Browse available businesses and services.
- Book appointments online.
- View appointment history.
- Track appointment status.
- Access digital queue information.

### 📋 Queue Management
- Digital queue and token management.
- Waiting list management.
- Queue overview.
- Appointment status management.
- Saved demo queue preview.

### 📅 Appointment Management
- Online appointment booking.
- Appointment scheduling.
- View and manage appointments.
- Customer appointment history.
- Search customers using name, email, phone number, or appointment ID.

### 🔐 Authentication
- Separate customer and administrator portals.
- Login and registration.
- Token-based authentication using JWT.
- Protected application routes.

## 🛠️ Technologies Used

### Frontend
- React 19
- React DOM
- React Router DOM
- JavaScript
- CSS3
- Vite
- Axios

### Backend
- Python
- Flask
- Flask-CORS
- Flask-SQLAlchemy
- SQLAlchemy
- Gunicorn

### Database
- PostgreSQL
- Supabase
- psycopg2

### Authentication & Configuration
- PyJWT
- python-dotenv

### Testing & Development
- Pytest
- Vitest
- React Testing Library
- ESLint

### Deployment
- Vercel

## 🏗️ Project Architecture

QueueLess follows a frontend-backend architecture:

1. **Frontend:** React application provides the customer and administrator interfaces.
2. **Backend:** Flask handles API requests, authentication, business operations, and appointment management.
3. **Database:** PostgreSQL stores application data and is hosted using Supabase.
4. **Deployment:** Vercel is used to deploy the application.

## 📂 Project Structure

```text
QueueLess/
│
├── backend/
│   ├── app/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── extensions.py
│   │
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   │
│   ├── package.json
│   └── index.html
│
├── database/
├── vercel.json
└── README.md
```

## ⚙️ Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Vinay9686803463/QueueLess.git
```

### 2. Navigate to the Project

```bash
cd QueueLess
```

### 3. Backend Setup

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

**Windows:**
```bash
.venv\Scripts\activate
```

**Linux / macOS:**
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required environment variables in the backend `.env` file, including the PostgreSQL `DATABASE_URL` and authentication settings.

Start the backend using the project's Flask entry point.

### 4. Frontend Setup

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

### 5. Build Frontend

```bash
npm run build
```

## 🗄️ Database

QueueLess uses PostgreSQL for persistent application data.

Supabase provides the hosted PostgreSQL database.

Database configuration is managed through environment variables. Do not upload `.env` files or database credentials to GitHub.

---

## 🚀 Deployment

Student Support AI can be deployed to a compatible hosting platform, depending on the repository's deployment configuration.

### Deployment checklist

1. Push the reviewed changes to the GitHub repository.
2. Connect the repository to the chosen hosting platform.
3. Configure the required environment variables in the hosting dashboard.
4. Configure the database and persistent storage where needed.
5. Verify AI provider configuration and network access.
6. Deploy and inspect application logs.
7. Test login, study materials, chat responses, and other important features.

### ⚠️ Production considerations

- Keep all API keys and application secrets server-side.
- Configure a persistent database for production data.
- Verify that uploaded study materials and generated indexes are stored appropriately.
- Test database migrations and recovery procedures before applying them to production.

---

## 🌐 Project Links

| Resource | Link |
|---|---|
| 🚀 **Live Demo** | [QueueLess](https://queueless-alpha-six.vercel.app/) |
| 💻 **GitHub Repository** | [QueueLess Repository](https://github.com/Vinay9686803463/QueueLess) |

---

## 🎯 Project Goal

The main goal of QueueLess is to make appointment scheduling and queue management easier for businesses and customers by providing a centralized digital platform.

---

**QueueLess – Book Smart. Wait Less.** 

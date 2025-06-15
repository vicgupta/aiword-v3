import uvicorn
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv()

hour=9
minute=56

from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# --- Environment Variables for Email ---
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.hostinger.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")


# --- SQLModel Models ---
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    joined_date: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class Word(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: str
    example: str
    # published_date: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    published_date: str = Field(unique=True)

class UserCount(BaseModel):
    count: int

class BulkResponse(BaseModel):
    message: str

# --- Database Setup ---
DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- NEW: Lifespan Context Manager ---
scheduler = BackgroundScheduler(timezone=pytz.timezone('US/Eastern'))

async def lifespan(app: FastAPI):
    # Code to run on application startup
    print("Application startup...")
    create_db_and_tables()
    # Schedule the job to run every day at 5:00 AM Eastern Time
    scheduler.add_job(send_daily_word_job, 'cron', hour=hour, minute=minute)
    scheduler.start()
    print(f"Scheduler started. Job is scheduled to run daily at {hour}:{minute} Eastern.")
    
    yield
    
    # Code to run on application shutdown
    print("Application shutdown...")
    scheduler.shutdown()
    print("Scheduler shut down.")

# --- FastAPI App Initialization ---
# The lifespan manager is passed here instead of using decorators
app = FastAPI(lifespan=lifespan)

origins = [
    "https://www.hiblazar.com",
    # "https://www.your-production-frontend.com",
    # "http://localhost:7000",
    "http://127.0.0.1:5500"
]

# --- 3. Add the CORSMiddleware to your application ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"], # Specify which methods are allowed
    allow_headers=["*"], # Allow all headers
)

# --- API Endpoints ---
def get_session():
    with Session(engine) as session:
        yield session

@app.post("/users", response_model=User)
def create_user(user: User, session: Session = Depends(get_session)):
    existing_user = session.exec(select(User).where(User.email == user.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.get("/users/count", response_model=UserCount)
def get_users_count(session: Session = Depends(get_session)):
    """
    Returns the total number of registered users.
    """
    # Using func.count() is an efficient way to get the row count from the database
    count = session.exec(select(func.count(User.id))).one()
    return {"count": count}

@app.post("/words", response_model=Word)
def create_word(word: Word, session: Session = Depends(get_session)):
    session.add(word)
    session.commit()
    session.refresh(word)
    return word

@app.get("/words", response_model=list[Word])
def get_words(session: Session = Depends(get_session)):
    words = session.exec(select(Word)).all()
    return words

@app.post("/words/bulk", response_model=BulkResponse)
def create_bulk_words(words: List[Word], session: Session = Depends(get_session)):
    """
    Accepts a list of word objects and adds them to the database.
    """
    try:
        for word in words:
            session.add(word)
        session.commit()
        return {"message": f"Successfully added {len(words)} words."}
    except Exception as e:
        # If any word fails, rollback the entire transaction
        print ("Error: ", e)
        session.rollback()
        # You might want to log the full error `e` on the server for debugging
        raise HTTPException(status_code=400, detail="An error occurred during bulk upload. No words were added.")

@app.get("/words/today", response_model=Word)
def get_today_word_endpoint(session: Session = Depends(get_session)):
    """
    Returns the single word of the day.
    The logic is centralized in the get_word_of_the_day function.
    """
    word = get_word_of_the_day(session)
    if not word:
        raise HTTPException(status_code=404, detail="Word of the day not found.")
    return word


# --- Helper Functions & Scheduled Job ---
def get_word_of_the_day(session: Session) -> Optional[Word]:
    """
    Reusable function to get the most recently published word.
    """
    today = str(datetime.now(pytz.timezone('US/Eastern')).date())
    word_is = session.exec(select(Word).where(Word.published_date == today)).first()
    # word_is = session.exec(select(Word).order_by(Word.published_date.desc())).first()
    return word_is

def send_email_to_recipients(subject: str, content: dict, recipients: List[str]):
    """
    Sends a multipart email (HTML with a plain-text fallback) to a list of recipients.
    """
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        print("SMTP environment variables not configured. Skipping email job.")
        return

    print(f"Starting email job to send to {len(recipients)} recipients...")
    
    # Create the plain-text and HTML versions of the message
    plain_text_body = f"""
    Word of the Day: {content['title']}
    ===================================

    Description:
    {content['description']}

    Example:
    "{content['example']}"

    Have a great day!
    """

    html_body = f"""
    <html>
      <head></head>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9;">
          <h1 style="font-size: 24px; color: #1a1a1a; border-bottom: 2px solid #eee; padding-bottom: 10px;">Word of the Day</h1>
          <h2 style="font-size: 28px; color: #0056b3; margin-top: 20px;">{content['title']}</h2>
          
          <h3 style="font-size: 16px; color: #333; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">DESCRIPTION</h3>
          <p style="font-size: 16px;">{content['description']}</p>
          
          <h3 style="font-size: 16px; color: #333; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">EXAMPLE</h3>
          <blockquote style="border-left: 4px solid #0056b3; padding-left: 15px; margin-left: 0; font-style: italic; color: #555;">
            {content['example']}
          </blockquote>
          
          <hr style="border: none; border-top: 1px solid #eee; margin-top: 30px;">
          <p style="color: #888; font-size: 12px; text-align: center;">Have a great day!</p>
        </div>
      </body>
    </html>
    """
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            for recipient in recipients:
                # Create a new message for each recipient
                msg = EmailMessage()
                msg['Subject'] = subject
                msg['From'] = SENDER_EMAIL
                msg['To'] = recipient

                # Set the plain text body
                msg.set_content(plain_text_body)

                # Add the HTML version. Email clients will prefer this.
                msg.add_alternative(html_body, subtype='html')
                
                server.send_message(msg)
                # print(f"Email sent to {recipient}")
        print("Email job finished successfully.")
    except Exception as e:
        print(f"An error occurred while sending emails: {e}")

def send_daily_word_job():
    """
    The scheduled job. Uses the helper functions to get data and send email.
    """
    print(f"Running scheduled job: send_daily_word_job at {datetime.now(pytz.timezone('US/Eastern'))}")
    with Session(engine) as session:
        daily_word = get_word_of_the_day(session)
        if not daily_word:
            print("Job aborted: No word of the day found.")
            return

        users = session.exec(select(User)).all()
        recipient_emails = [user.email for user in users]
        if not recipient_emails:
            print("Job aborted: No users to email.")
            return

        subject = f"Word of the Day: {daily_word.title}"
        content = {
            "title": daily_word.title,
            "description": daily_word.description,
            "example": daily_word.example
        }
        send_email_to_recipients(subject, content, recipient_emails)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
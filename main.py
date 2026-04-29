import os
from fastapi import FastAPI, Form, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv
import stripe
import db
import heuristics

SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "0.7"))

load_dotenv()
db.init_db()

app = FastAPI(title="SpamBlock")
templates = Jinja2Templates(directory="templates")

PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")

if STRIPE_KEY:
    stripe.api_key = STRIPE_KEY

PLAN_PRICES = {"solo": 29, "business": 79, "agency": 199}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, plan: str = "solo"):
    plan = plan if plan in PLAN_PRICES else "solo"
    return templates.TemplateResponse(
        "signup.html",
        {"request": request, "plan": plan, "price": PLAN_PRICES[plan]},
    )


@app.post("/signup")
async def signup_submit(
    name: str = Form(...),
    email: str = Form(...),
    forward_to: str = Form(...),
    plan: str = Form("solo"),
):
    if not (TWILIO_SID and TWILIO_TOKEN):
        raise HTTPException(500, "Twilio not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")

    twilio = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
    available = twilio.available_phone_numbers("US").local.list(limit=1)
    if not available:
        raise HTTPException(500, "No Twilio numbers available.")

    purchased = twilio.incoming_phone_numbers.create(
        phone_number=available[0].phone_number,
        voice_url=f"{PUBLIC_URL}/voice/incoming",
        voice_method="POST",
    )

    db.add_customer(name, email, purchased.phone_number, forward_to)

    if STRIPE_KEY and STRIPE_PRICE_ID:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            customer_email=email,
            subscription_data={"trial_period_days": 7},
            success_url=f"{PUBLIC_URL}/welcome?number={purchased.phone_number}",
            cancel_url=f"{PUBLIC_URL}/signup?plan={plan}",
        )
        return RedirectResponse(session.url, status_code=303)

    return RedirectResponse(f"/welcome?number={purchased.phone_number}", status_code=303)


@app.get("/welcome", response_class=HTMLResponse)
def welcome(number: str = ""):
    return f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:80px auto;padding:20px;text-align:center">
      <h1>You're live 🎉</h1>
      <p style="font-size:18px">Your SpamBlock business number is:</p>
      <h2 style="font-size:32px;color:#10b981">{number}</h2>
      <p>Spam calls to this number will be auto-rejected. Real callers get forwarded to your phone.</p>
      <p style="color:#64748b">Use this number on your website, Google Business listing, and business cards.</p>
    </body></html>
    """


@app.post("/voice/incoming")
async def incoming_call(From: str = Form(...), To: str = Form(...), CallSid: str = Form(...)):
    response = VoiceResponse()
    customer = db.get_customer_by_twilio_number(To)
    if not customer:
        response.say("This number is not configured. Goodbye.")
        response.hangup()
        return _twiml(response)

    spam, reason = db.is_spam(From)
    if spam:
        db.log_call(customer["id"], From, To, "blocked", f"db:{reason}")
        response.reject(reason="busy")
        return _twiml(response)

    h_spam, h_reason, h_confidence = heuristics.check(From, customer["twilio_number"])
    if h_spam and h_confidence >= SPAM_THRESHOLD:
        db.log_call(customer["id"], From, To, "blocked", f"heuristic:{h_reason}({h_confidence})")
        response.reject(reason="busy")
        return _twiml(response)

    db.log_call(customer["id"], From, To, "forwarded", "clean")
    response.say("Connecting your call.", voice="Polly.Joanna")
    response.dial(customer["forward_to"], timeout=20, caller_id=To)
    return _twiml(response)


@app.post("/admin/report-spam")
async def report_spam(phone: str = Form(...), source: str = Form("user_report")):
    db.add_spam_number(phone, source)
    return {"ok": True, "phone": phone}


def _twiml(response: VoiceResponse) -> Response:
    return Response(content=str(response), media_type="application/xml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)

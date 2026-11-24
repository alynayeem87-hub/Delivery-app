import io
import json
import os
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
import gspread
from PIL import Image

app = FastAPI()

FIELDS = [
    "Ticket Number",
    "Date",
    "Time In",
    "Time Out",
    "Truck Number",
    "Customer",
    "Transporter",
    "Material",
    "Destination",
    "Driver Name",
    "Empty Weight (Kg)",
    "Gross Weight (Kg)",
    "Net Weight (Kg)",
]


def get_worksheet():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    return sh.sheet1


def extract_slip_data(image_bytes: bytes) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    image = Image.open(io.BytesIO(image_bytes))

    prompt = (
        "Extract the exact values from this weighbridge / delivery note image "
        "without changing or converting units or formats. Return ONLY valid JSON "
        "with these exact keys:\n"
        + json.dumps(FIELDS)
        + '\nIf a field is blank or not present, use empty string "".'
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return json.loads(response.text)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Delivery Note Upload</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 480px; margin: 40px auto; padding: 20px; }
            button { padding: 12px; font-size: 16px; cursor: pointer; margin-top: 12px; width: 100%; }
            pre { background: #f4f4f4; padding: 12px; border-radius: 6px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h2>Upload Delivery Note</h2>
        <form id="uploadForm">
            <input type="file" id="fileInput" name="file" accept="image/*" required />
            <button type="submit">Upload & Add Row</button>
        </form>
        <p id="status"></p>
        <pre id="result"></pre>

        <script>
            document.getElementById("uploadForm").addEventListener("submit", async (e) => {
                e.preventDefault();
                const fileInput = document.getElementById("fileInput");
                if (!fileInput.files.length) return;

                const status = document.getElementById("status");
                const result = document.getElementById("result");
                status.textContent = "Reading slip...";
                result.textContent = "";

                const formData = new FormData();
                formData.append("file", fileInput.files[0]);

                const res = await fetch("/upload", { method: "POST", body: formData });
                const data = await res.json();

                if (res.ok) {
                    status.textContent = "Saved in Google Sheet!";
                    result.textContent = JSON.stringify(data.extracted_data, null, 2);
                    fileInput.value = "";
                } else {
                    status.textContent = "Error: " + (data.detail || "Failed");
                }
            });
        </script>
    </body>
    </html>
    """


@app.post("/upload")
async def upload_delivery_note(file: UploadFile = File(...)):
    content = await file.read()
    extracted = extract_slip_data(content)
    ws = get_worksheet()
    row_values = [extracted.get(field, "") for field in FIELDS]
    ws.append_row(row_values, value_input_option="USER_ENTERED")
    return {"extracted_data": extracted}

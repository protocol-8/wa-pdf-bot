"""
WhatsApp → PDF Converter Bot
Uses Meta WhatsApp Cloud API (free) — sends actual PDF files, no links.
"""

import os
import tempfile
import subprocess
import requests
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Env vars (set these on Railway) ─────────────────────────────────────────
WA_TOKEN        = os.environ.get("WA_TOKEN")           # Meta permanent access token
WA_PHONE_ID     = os.environ.get("WA_PHONE_ID")        # WhatsApp Phone Number ID
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN")  # any string you choose

API_URL = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}"
SUPPORTED = {".docx", ".doc", ".pptx", ".ppt"}


# ── Send a text message ──────────────────────────────────────────────────────
def send_text(to: str, text: str):
    requests.post(
        f"{API_URL}/messages",
        headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}},
    )


# ── Upload PDF to Meta and get a media ID ───────────────────────────────────
def upload_pdf(pdf_path: str, filename: str) -> str | None:
    try:
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                f"{API_URL}/media",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                files={"file": (filename, f, "application/pdf")},
                data={"messaging_product": "whatsapp"},
            )
        data = resp.json()
        return data.get("id")
    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return None


# ── Send PDF file using media ID ─────────────────────────────────────────────
def send_pdf(to: str, media_id: str, filename: str):
    requests.post(
        f"{API_URL}/messages",
        headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": filename,
                "caption": f"✅ Here's your converted PDF!"
            },
        },
    )


# ── Download a file sent by user via WhatsApp ────────────────────────────────
def download_wa_file(media_id: str, dest_path: str) -> bool:
    try:
        # Step 1: get the download URL
        url_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
        )
        download_url = url_resp.json().get("url")
        if not download_url:
            return False

        # Step 2: download the actual file
        file_resp = requests.get(
            download_url,
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            timeout=60,
        )
        file_resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(file_resp.content)
        return True
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return False


# ── Convert file to PDF using LibreOffice ────────────────────────────────────
def convert_to_pdf(input_path: str, output_dir: str) -> str | None:
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, input_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            pdf_path = os.path.join(output_dir, Path(input_path).stem + ".pdf")
            if os.path.exists(pdf_path):
                return pdf_path
        print(f"[ERROR] LibreOffice: {result.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print("[ERROR] Conversion timed out")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


# ── Webhook verification (Meta requires this once during setup) ──────────────
@app.route("/webhook", methods=["GET"])
def verify():
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403


# ── Main webhook — receives WhatsApp messages ────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]["value"]
        messages = changes.get("messages", [])

        if not messages:
            return jsonify({"status": "ok"}), 200

        msg      = messages[0]
        from_num = msg["from"]
        msg_type = msg.get("type")

        # Not a document
        if msg_type != "document":
            send_text(from_num,
                "👋 Hi! Send me a *.docx*, *.doc*, *.pptx*, or *.ppt* file and I'll convert it to PDF for you! 📄"
            )
            return jsonify({"status": "ok"}), 200

        # Get file info
        doc      = msg["document"]
        media_id = doc["id"]
        filename = doc.get("filename", f"file_{media_id}")
        ext      = Path(filename).suffix.lower()

        if ext not in SUPPORTED:
            send_text(from_num,
                f"⚠️ Sorry, I can't convert *{filename}*.\n\nSupported formats: .docx, .doc, .pptx, .ppt"
            )
            return jsonify({"status": "ok"}), 200

        # Let her know we're working on it
        send_text(from_num, f"⏳ Converting *{filename}*... give me a sec!")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, filename)

            # Download file
            if not download_wa_file(media_id, input_path):
                send_text(from_num, "❌ Couldn't download your file. Please try sending it again.")
                return jsonify({"status": "ok"}), 200

            # Convert to PDF
            pdf_path = convert_to_pdf(input_path, tmpdir)
            if not pdf_path:
                send_text(from_num, "❌ Conversion failed. Make sure the file isn't password-protected and try again.")
                return jsonify({"status": "ok"}), 200

            # Upload PDF to Meta
            pdf_filename = Path(filename).stem + ".pdf"
            media_id_out = upload_pdf(pdf_path, pdf_filename)
            if not media_id_out:
                send_text(from_num, "❌ Converted but failed to send. Please try again.")
                return jsonify({"status": "ok"}), 200

            # Send PDF back!
            send_pdf(from_num, media_id_out, pdf_filename)

    except (KeyError, IndexError):
        pass  # Ignore non-message webhooks (delivery receipts, etc.)

    return jsonify({"status": "ok"}), 200


# ── Health check ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return "✅ PDF Bot is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

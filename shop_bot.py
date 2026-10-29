from flask import Flask, request
import os
from openai import OpenAI

app = Flask(name)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route("/", methods=["GET"])
def home():
return "Al Sadiq Center Bot is running!"

@app.route("/chat", methods=["POST"])
def chat():
data = request.get_json(silent=True) or {}
message = data.get("message", "")

if not message:
    return {"error": "اكتب رسالتك أولاً"}, 400

response = client.responses.create(
    model="gpt-4.1-mini",
    instructions="أنت موظف مبيعات ودود في متجر الصادق سنتر للملابس. تحدث بالعربية، واسأل عن نوع الملابس والمقاس واللون. لا تخترع أسعاراً أو مخزوناً غير معروف.",
    input=message
)

return {"reply": response.output_text}

if name == "main":
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

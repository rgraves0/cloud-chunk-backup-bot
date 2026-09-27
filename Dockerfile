FROM python:3.11-slim

# Root မဟုတ်သော သီးသန့် User ဖန်တီးခြင်း (လုံခြုံရေးအတွက်)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# ဖိုင်ခွဲထုတ်ရန် p7zip သာ သွင်းယူပြီး မလိုအပ်သော cache များကို ရှင်းလင်းခြင်း
RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ဖိုင်များ ယာယီသိမ်းမည့် folder ပြုလုပ်ပြီး Permission ပေးခြင်း
RUN mkdir -p /app/downloads && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

CMD ["python", "main.py"]

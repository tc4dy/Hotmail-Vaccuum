🔥 Hotmail VACCUUM

> Dynamic, fast & friendly Hotmail/Outlook account checker

✨ Features
- 🧠 Fully dynamic – grabs fresh PPFT tokens every time
- 🚀 Multi‑threaded (up to 500 threads)
- 🛡️ Optional delay to avoid IP bans
- 🌍 Proxy support (HTTP/HTTPS/SOCKS4/SOCKS5)
- 🔁 Resume – continues where you left off
- 📁 Saves valid, 2FA & invalid combos
- 📊 Generates a neat report with stats
- 🎨 Vibrant, eye‑friendly CLI
- 🤖 Discord webhook integration

Use Residental Proxy Because:

📊 Test results with 10,000 combos:

Without a proxy:
├── Duration: 1–2 minutes (followed by an IP ban)
├── Completed combos: ~100–200
└── Success rate: 1–2%

Datacenter Proxy:
├── Duration: 30–60 minutes (quick ban)
├── Completed combos: ~2,000–3,000
└── Success rate: ~30–40%

Residential Proxy:
├── Runtime: Stable for days
├── Completed combos: All 10,000
└── Success rate: 95%+

 🚀 Quick start

```bash
git clone https://github.com/tc4dy/Hotmail-Vaccuum.git
cd Hotmail-Vaccuum
pip install -r requirements.txt
```

Place your combos in combos.txt (format: email:password).
Then run:
```bash
python main.py
```
📂 Output

    hits.txt – working accounts (no 2FA)

    2fa.txt – accounts that need 2FA

    invalid.txt – dead combos

    report.txt – full statistics

🤝 Contributing

Feel free to open issues or pull requests. Keep it friendly 🫶

⚠️ Disclaimer

For educational purposes only. The user is responsible.

Made with ☕ by @tc4dy

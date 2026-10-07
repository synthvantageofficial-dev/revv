# 🔋 Startup Project — EV Battery Health Certification (India)

> **एक लाइन में:** पुरानी (used) EV की battery की सच्ची सेहत (health) जाँचकर एक भरोसेमंद
> **"Battery Health Certificate"** देना — जैसे इंसान की blood-test report या गाड़ी का CarFax,
> बस EV की battery के लिए। India में ये independent, हर-brand वाली कुर्सी अभी लगभग खाली है।

**Status:** Idea final. Development शुरू। (तय: 2026-09-29)
**Startup नाम:** **Revv** ⚡ (तय: 2026-10-02)

## 📂 Project structure / Progress
```
ev cars/
  CLAUDE.md          # यही फाइल — पूरी दिशा
  landing/
    index.html       # ✅ one-page landing — LIVE: https://revv-ev.netlify.app
                     #    Netlify site "revv-ev" (siteId 77e3484e-6e9a-421f-b79c-d1aadadf67e9)
                     #    waitlist form detected → emails Netlify dashboard में आते हैं
  engine/            # ✅ core battery health scoring engine (Python, v1)
    revv_engine/     #    models.py, scoring.py, certificate.py
    demo.py          #    `python demo.py` → 3 sample EVs के certificates
    tests/           #    `python -m unittest discover -s tests` (7 tests pass)
    README.md
  app/               # ✅ software layer + operator + buyer pages (पूरा flow चलता है)
    device.py        #    नकली OBD dongle (raw data) — असली आने पर बस यही बदलेगा
    specs.py         #    vehicle spec DB — model से capacity/chemistry/baseline auto-lookup
    ingest.py        #    translator: raw messy data → engine का साफ format (specs इस्तेमाल करता है)
    store.py         #    certificates को save करता है (JSON; बाद में DB) → verifiable
    server.py        #    stdlib server: `python server.py` → :8130
    web/index.html   #    operator console: dongle scan → certificate + buyer-link
    web/manual.html  #    manual/assisted entry — बिना dongle, हाथ से data → certificate
    web/certificate.html #  buyer page: /c/<id> → read-only verified certificate
    web/cert.css /cert.js #  shared design + render (सब pages एक ही)
```
**Routes:** `/` operator · `/manual` manual entry · `/c/<id>` buyer certificate (QR) ·
`/api/score` · `/api/certificate?id=` (verify, unknown→404) · `/api/models` (spec list)।

## 🗂️ Code roadmap (real-data के बिना — पहले ये सब निपटाना है)
1. ✅ Vehicle spec database (specs.py)
2. ✅ Manual/assisted entry (/manual)
3. ✅ Dashboard / history (/dashboard — stats tiles, verdict distribution, search, table)
4. ✅ PDF export (print letterhead+footer, page-break safe; "Download PDF")
5. ✅ Operator login/accounts (auth.py — PBKDF2 + signed-cookie; /login; buyer page public;
     हर cert पर issued_by; default creds app/data/DEFAULT_LOGIN.txt)
6. ✅ Revoke/expiry + config (config.py — company/verify-base/validity; हर cert पर
     status + valid_until; dashboard पर Revoke button; buyer page revoked/expired banner)
7. ✅ Input validation + error states (ingest.validate — साफ messages; friendly 404)
8. ✅ Data-logging pipeline (datalog.py → data/readings_log.jsonl; /api/export.csv)
9. ⬜ (बाद में, user कहे तब) app host/deploy

### ✅ पूरा CODE हिस्सा complete! अब सिर्फ Phase 2/3 बचा:
- असली OBD dongle + हर-brand parsing (device.py replace)
- असली गाड़ियों से data → engine calibrate (AgeingParams tune — data अब datalog में अपने आप जमा होगा)

> app/data/ में secrets + certs + log हैं → .gitignore में।
> नई files: config.py, datalog.py, auth.py, specs.py, store.py; web/: login, manual, dashboard, certificate, cert.css/js, nav.js।
> असली OBD per-brand parsing + असली calibration = Phase 2/3 (असली data के साथ)।
**Certificate अब detailed:** vehicle, capacity+fade, per-cell (min/max/spread), internal
resistance ratio, cycles/year, fast-charge %, temp; "How Revv scored it" (calendar+cycle
loss + itemised penalties); data-quality % (measured vs missing); QR + verify-ID; raw
telemetry; Print/Save-PDF. Trust = transparency + neutrality + verifiable QR (govt stamp
नहीं, पर verifiable + independent)।
**बना हुआ:** (1) नाम Revv, (2) landing page, (3) engine v1 — transparent rule-based SoH
score + certificate, confidence system, warning flags। सारे constants `AgeingParams` में
(बाद में असली data से calibrate होंगे)।
**बाकी:** landing deploy (Netlify), engine को API में लपेटना, असली OBD fields define करना,
data जमा करके calibrate करना।

---

## 1. हम किस Problem का Solution निकाल रहे हैं

- पुरानी EV में सबसे कीमती चीज़ = **battery**। वो phone की battery की तरह धीरे-धीरे कमज़ोर होती है।
- खरीदने वाले को पता ही नहीं चलता battery अंदर से कितनी बची है (90% या 60%?).
- Battery बदलवाना = **₹2–4 लाख**। यानी बिना जाँचे used EV खरीदना = लाखों का जुआ।
- इसी डर से used-EV resale market अटका हुआ है।
- **कोई भरोसेमंद, neutral, independent बंदा नहीं है जो सच बता सके।** — यही gap हम भरेंगे।

---

## 2. हम असल में करते क्या हैं (Product)

- EV की battery की जाँच करके **"इस battery की health = 87%"** जैसा **certificate** देते हैं।
- **असली product = SOFTWARE + ALGORITHM** (जो कच्चे data को पढ़कर सच्चा health नंबर निकाले)।
- Device खुद नहीं बनाना — वो market में पहले से मौजूद है (नीचे देखो)।

### कैसे जाँचते हैं — 2 रास्ते
- **रास्ता A (Software-only, Recurrent-style):** connected/नई गाड़ियाँ अपना data भेजती हैं →
  हमारा software score निकाल दे। **Zero hardware, सिर्फ laptop + algorithm.**
- **रास्ता B (हल्का device, Aviloo-style):** market से सस्ता **OBD dongle (₹500–₹3000)** खरीदो →
  गाड़ी के OBD port में लगाओ → 3 मिनट में data → हमारा software → certificate।

> ⚠️ हमें device **बनाना नहीं, खरीदना** है। Factory / manufacturing / करोड़ों की funding **नहीं** चाहिए।

---

## 3. Customers कौन और वो पैसे क्यों देंगे (Revenue)

एक ही "battery का नंबर" — 4 अलग लोगों को बेचेंगे, क्योंकि हर एक का अपना डर है:

| Customer | उसका डर | वो पैसे क्यों देगा |
|---|---|---|
| **1. Used-EV खरीदने वाला आम आदमी** | "battery कबाड़ न निकले" | ₹हज़ार का certificate → ₹लाखों का धोखा बचाया |
| **2. Used-car platforms (Spinny, Cars24, OLX)** | "customer भरोसा नहीं करता, EV बिकती नहीं" | certificate से गाड़ी जल्दी + महँगी बिकती है (fee/subscription) |
| **3. Banks / NBFC (loan वाले)** | "battery खराब हुई तो गाड़ी की कीमत गिरेगी, पैसा फँसेगा" | safe loan देने के लिए हमारा score चाहिए |
| **4. Insurance companies** | "premium कितना रखें?" | सही premium तय करने के लिए हमारा score चाहिए |

---

## 4. DIY क्यों नहीं चलेगा (हमारी असली value)

बंदा खुद dongle खरीदकर test क्यों नहीं करता? इसलिए:
1. **Device सिर्फ कच्चा/झूठा BMS नंबर देता है** — गाड़ी का BMS असली degradation छुपाता है।
   Aviloo का पूरा धंधा ही यही है कि वो BMS को नहीं मानते, खुद independent नंबर निकालते हैं।
2. **भरोसा / neutral third-party:** buyer-seller एक-दूसरे पर भरोसा नहीं करते, दोनों को एक
   बेईमानी न करने वाला बिचौलिया चाहिए (CarFax/inspection company जैसा)।
3. **मान्यता:** बंदे की खुद की रिपोर्ट कोई bank/insurance नहीं मानता; हमारा standardized
   certificate सब मानें — वही बिकता है।

> Example: थर्मामीटर घर में है, फिर भी medical certificate के लिए **lab** जाते हो।

---

## 5. Competition — दुनिया और India (सच्चाई)

### 🌍 Western (proven, पैसे कमा रहे — यानी model काम करता है)
| Company | देश | Launch | Funding | Model |
|---|---|---|---|---|
| **Recurrent** | USA (Seattle) | 2020 | ~$24M (Series A $16M) | software/data — battery "score", Cars.com/Edmunds पर |
| **Aviloo** | Austria | 2018 | ~$35.7M (Series C, €30M round) | OBD 3-min FLASH test → independent certificate; 750+ customers, 30+ देश |
| TWAICE | Germany | 2018 | ~$100M | battery analytics (OEM/grid — अलग segment) |
| Volytica / ACCURE | Germany | 2019 | छोटा/VC | fleet/grid analytics |

### 🇮🇳 India (कुर्सी लगभग खाली)
- **कोई national standard नहीं** (govt/NITI Aayog framework अभी notify नहीं हुआ)।
- OEM (Tata/MG/Hyundai/Ather) सिर्फ **अपनी ही गाड़ी** की रिपोर्ट देते हैं — independent नहीं।
- **Spinny + JSW MG** ने जुलाई 2026 में certified pre-owned शुरू किया — नया + एक brand तक सीमित।
- ev.care, BatteryOK (EV DOCTOR), EVPie — छोटे/early, कोई dominant भरोसेमंद independent नहीं।

> **निचोड़:** हम "दुनिया के पहले" नहीं (model proven है — अच्छी बात), पर **India में independent,
> cross-brand battery-certification के early/पहले गंभीर खिलाड़ी** — ये लगभग सच। जैसे Uber → Ola.

---

## 6. हमारा Moat (कोई copy क्यों नहीं कर पाएगा)

- असली मुश्किल manufacturing नहीं — **सटीक algorithm + battery DATA जमा करना।**
- जितना ज़्यादा data, उतना सटीक score। शुरू में data कम → मेहनत लगेगी।
- Factory कोई भी लगा ले, पर **हमारा data + algorithm कोई नहीं चुरा सकता** — यही दीवार है।

---

## 7. Timing क्यों सही है (अब क्यों, पहले क्यों नहीं)

- अब तक used EV थीं ही कम → ज़रूरत कम थी।
- 2020–2022 वाली पहली-wave EVs **अब used market में आ रही हैं** → माँग अभी बन रही है।
- सरकार भी battery-health framework पर सोच रही → आगे मान्यता बढ़ेगी।

---

## 8. ⚠️ सच्चाई (ताकि अंधेरे में न रहें)

- ✅ Model proven है (Recurrent/Aviloo)।  ✅ India में जगह खाली।  ✅ Timing बन रही।
- ⚠️ आसान ≠ मुफ़्त — असली काम: भरोसेमंद algorithm + data + trust बनाना।
- ⚠️ Risk: OEM / Spinny-Cars24 खुद ये करने लगें → इसलिए **independent + cross-brand + banks/insurance**
  वाला भरोसा जल्दी बनाना ज़रूरी।

---

## 9. जो शुरू में NHI करना (गलतफहमियाँ जो साफ हो चुकीं)

- ❌ Device/hardware manufacturing या factory — नहीं।
- ❌ करोड़ों की upfront funding — नहीं (एक शहर से, लाख-दो लाख में शुरू)।
- ❌ सैकड़ों employees / हर शहर में office — नहीं (2–4 लोग या partnership)।
- ❌ पूरे India में एक साथ launch — नहीं (एक शहर से pilot)।

---

## 10. Next Step (अभी तय होना बाकी — user के साथ discuss करना है)

- [ ] रास्ता A (software-only) या रास्ता B (OBD dongle) — कौन सा पहले?
- [ ] पहले 90 दिन का step-by-step plan (पहला test, पहला customer, कितना पैसा)।
- [ ] पहला customer segment किसे पकड़ें (आम आदमी vs used-car platform vs bank)?
- [ ] कौन से शहर से pilot?

---

## Sources (research के links)
- Recurrent: tracxn.com/d/companies/recurrent-auto ; mercomcapital.com (16M Series A)
- Aviloo: electrive.com (€30M, 2026-02-11) ; crunchbase.com/organization/aviloo
- Independent diagnostics gap (India): evreporter.com "missing link in EV battery management"
- Used EV no battery standard (India): vahanbazaar.in ; knowledge-sourcing.com (certified pre-owned India)
- Spinny + JSW MG certified pre-owned EV (July 2026)
- TWAICE funding: electrive.com (2026-02-05)

---
*यह फाइल हमारे startup की पूरी दिशा है — काम करते वक़्त इसे reference रखना। नई बात तय हो तो यहीं update करना।*

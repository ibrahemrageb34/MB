# Setup

المتطلبات: Python 3.10+ بس. مفيش `pip install`.

## 1. Meta token (System User)

1. Business Settings → Users → **System users** → Add (Admin).
2. Assign assets: الـ 7 Ad accounts (Manage campaigns) + الصفحات + حسابات Instagram.
3. Generate token على App بتاعك بالصلاحيات:
   `ads_read`, `ads_management` (لو هتستخدم `apply-spend-caps`), `business_management`, `pages_read_engagement`, `read_insights`, `instagram_basic`, `instagram_manage_insights`.
4. `export META_ACCESS_TOKEN="..."` (أو في n8n: Settings → Variables / env).

System user token مش بيخلص زي توكن المستخدم، ومش مربوط بحساب شخص ممكن يسيب الشغل.

## 2. الأكونتات

`cp config/accounts.example.json config/accounts.json` — لكل أكونت:

| الحقل | ليه مهم |
|---|---|
| `id` | `act_...` |
| `code` | كود قصير بيبدأ بيه اسم كل كامبين، واسم ملفات `data/*/<CODE>.json` |
| `business.objective` | `purchase` / `lead` / `message` — بيحدد "النتيجة" |
| `business.target_cpa` | **أهم رقم في السيستم.** للإيكومرس: AOV × الهامش × النسبة اللي تقبل تصرفها على الاستحواذ |
| `business.gross_margin` | عشان break-even ROAS = 1 ÷ الهامش |
| `business.monthly_budget` | الـ pacing والـ forecast |
| `ig_user_id` / `page_id` | تقييم البوستات الجديدة |
| `team` | أسماء المسؤولين (بتظهر في Team Layer) |
| `tracking.emq` | Event Match Quality من Events Manager (لحد ما يتربط أوتوماتيك) |
| `prepaid.manual_balance` | لو الرصيد مش بيتقري من الـ API |

الـ thresholds كلها في `config/settings.json`. لتعديلات محلية من غير ما تلمس الملف: `config/settings.local.json` بنفس الشكل.

## 3. التنبيهات

- **Telegram (الأسهل):** اعمل bot من @BotFather → `TELEGRAM_BOT_TOKEN`، وضيفه على جروب الفريق → `TELEGRAM_CHAT_ID`.
- **WhatsApp / Slack / Email:** `MBOS_WEBHOOK_URL` = Webhook في n8n. الملف `n8n/05_webhook_to_whatsapp.json` بيبعت على WhatsApp Cloud API (`WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_TO`). ملحوظة: الرسالة الحرة بتشتغل بس لو الرقم كلّمك في آخر 24 ساعة؛ غير كده لازم Template متوافق عليه.

## 4. الجدولة

- **n8n:** Import الملفات من `n8n/`. عدّل المسار `/opt/MB`. نود Execute Command متقفلة افتراضياً في الإصدارات الجديدة من n8n (self-hosted بس) — لازم تسمح بيها في إعدادات السيرفر، أو استخدم cron.
- **cron:** `n8n/crontab.example`.

## 5. Claude (اختياري)

`export ANTHROPIC_API_KEY=...` — التحليل النوعي للبوستات الجديدة بيشتغل لوحده. الموديل في `config/settings.json → ai.model`. لو المفتاح مش موجود السيستم بيشتغل بالقواعد بس.

## 6. بديل من غير كود للداتا

لو مش عايز تدير توكن ميتا، Windsor.ai (أو Supermetrics) ممكن يسحب داتا الأكونتات لـ BigQuery/Sheets. ساعتها محتاج connector صغير يقرا من هناك ويطلع نفس شكل `rows` اللي في `connectors/meta.py`.

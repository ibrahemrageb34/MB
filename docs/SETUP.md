# Setup

المتطلبات: Python 3.10+ بس. مفيش `pip install`.

## 1. Meta token (System User)

1. Business Settings → Users → **System users** → Add (Admin).
2. Assign assets: الـ 7 Ad accounts (Manage campaigns) + الصفحات + حسابات Instagram.
3. Generate token على App بتاعك بالصلاحيات:
   `ads_read`, `ads_management` (لو هتستخدم `apply-spend-caps`), `business_management`, `pages_read_engagement`, `read_insights`, `instagram_basic`, `instagram_manage_insights`.
4. `export META_ACCESS_TOKEN="..."` (أو في n8n: Settings → Variables / env).

System user token مش بيخلص زي توكن المستخدم، ومش مربوط بحساب شخص ممكن يسيب الشغل.

### الأكونتات موزعة على أكتر من Business Manager

**الحل الأفضل: Business Manager واحد بتاعك، والباقيين يعملوه Partner.**
1. اعمل (أو استخدم) Business Manager باسمك/باسم شغلك.
2. كل صاحب BM (الإيجنسي أو العميل) يدخل: Business Settings → **Partners** → Add → يحط **Business ID** بتاعك → يشارك الأد أكونت (Manage campaigns + View performance + **Manage billing** عشان الرصيد) + الصفحة + حساب الإنستجرام.
3. في الـ BM بتاعك: System User واحد، وتعمله Assign على كل الأصول اللي اتشاركت.
4. توكن واحد يغطي الكل. حطه في `META_TOKEN_BM1` و`META_TOKEN_BM2` و`META_TOKEN_BM3` كلهم (نفس القيمة).

**لو صاحب BM رفض المشاركة:** اعمل System User جوه الـ BM بتاعه (لازم تكون Admin فيه) وخد توكن منفصل. كل أكونت في `accounts.json` فيه `token_env` بيحدد يستخدم أنهي توكن.

**الرصيد:** قراءة رصيد الدفع المسبق محتاجة صلاحية على الـ Billing. لو مش متاحة، حط `prepaid.manual_balance` في الأكونت وحدّثه بعد كل شحن.

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
| `facebook_page` | لينك الصفحة. السيستم بيجيب منه الـ Page ID وحساب الإنستجرام المربوط لوحده |
| `lanes` | الأكونت ممكن يشتغل على أكتر من هدف (رسايل + مبيعات موقع). كل lane بتارجت منفصل. الكامبين بتتوزع حسب الـ optimization بتاعها، أو بكلمة في اسمها (`keywords`) |
| `brand_targets` | أهداف البراند الحقيقية: `monthly_sales`, `target_mer`, `target_cpql` |
| `token_env` | أنهي توكن (لو الأكونتات في أكتر من Business Manager) |
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

## 4.1 الرفع على هوست

**لازم يكون VPS (Ubuntu) مش استضافة مواقع عادية:** السيستم محتاج Python و cron، وأغلب استضافات cPanel بتقفل ده أو بتحدّه.

```bash
sudo apt update && sudo apt install -y python3 git
sudo git clone https://github.com/ibrahemrageb34/MB.git /opt/MB && cd /opt/MB
# ارفع config/accounts.json (مش موجود في الريبو) من جهازك:
#   scp config/accounts.json user@SERVER:/opt/MB/config/
cp deploy/env.example .env && chmod 600 .env && nano .env      # التوكنز هنا فقط
python3 -m mbos run --no-notify                                  # أول تجربة
crontab n8n/crontab.example                                      # الجدولة
```

الداشبورد فيه أرقام العملاء: متحطوش على لينك مفتوح. `deploy/nginx-dashboard.conf` بيحميه بباسورد.

⚠️ **الريبو ده Public على GitHub.** عشان كده `accounts.json` والتوكنز وأي داتا عملاء في `data/` متجاهلين في `.gitignore` ومش بيترفعوا. الأحسن تخلي الريبو Private: Settings → General → Danger Zone → Change visibility.

## 4.2 شيت المبيعات (عشان ROAS حقيقي للمعرض والواتساب)

ميتا مش شايفة المبيعات اللي بتحصل في المعرض أو على الواتساب. من غير الشيت، أقصى حاجة السيستم يقولها: "تكلفة المحادثة كام"، مش "المحادثة جابت فلوس كام".

1. Google Sheet لكل براند بالأعمدة اللي في `data/sales/TEMPLATE.csv`: `date, source, orders, revenue, leads, qualified_leads, deals, notes`.
2. `source`: showroom / whatsapp / messenger / website / walk_in / other.
3. File → Share → **Publish to web** → الشيت → **CSV** → انسخ اللينك.
4. في `accounts.json`: `"sales_log": {"csv_url": "اللينك"}`.
5. حد من الفريق يسجّل كل يوم (دقيقتين).
6. لينك Publish to web مش متخمّن بس أي حد معاه يقدر يفتحه. لو الأرقام حساسة: نزّل الشيت CSV على السيرفر واستخدم `"sales_log": {"file": "data/sales/CODE.csv"}` بدل اللينك. السيستم بينبّه لو الشيت متحدّثش من أكتر من يومين.

## 5. Claude (اختياري)

`ANTHROPIC_API_KEY` في `.env` بيشغّل حاجتين: (1) تحليل كل بوست جديد (الهوك، الزاوية، العرض، الاعتراضات)، (2) **تصنيف الإعلانات اللي مش متسمية بالـ naming convention** (Angle / Format / Hook / Offer) من نص الإعلان، والنتيجة بتتحفظ في `data/tags/` عشان كل إعلان يتصنف مرة واحدة بس. الموديل في `config/settings.json → ai.model`. لو المفتاح مش موجود السيستم بيشتغل بالقواعد بس.

## 6. بديل من غير كود للداتا

لو مش عايز تدير توكن ميتا، Windsor.ai (أو Supermetrics) ممكن يسحب داتا الأكونتات لـ BigQuery/Sheets. ساعتها محتاج connector صغير يقرا من هناك ويطلع نفس شكل `rows` اللي في `connectors/meta.py`.

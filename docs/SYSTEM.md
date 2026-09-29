# المعمارية ومنطق كل موديول

## المبدأ

**Business → Customer → Offer → Funnel → Measurement → Creative → Media → Optimization → Scaling.**
عشان كده كل أكونت في `config/accounts.json` لازم يبدأ بـ `business`: الهدف (purchase / lead / message)، AOV، الهامش، **التارجت CPA**، الميزانية الشهرية.
كل حكم في السيستم نسبي للتارجت ده. "CPR 300" مش حلو ولا وحش لوحده؛ هو 0.75× أو 1.4× التارجت.

## الموديولات

| الموديول | الملف | بيجاوب على | المنطق |
|---|---|---|---|
| Data cleaning | `engine/cleaning.py` | هل الداتا نضيفة؟ | إزالة التكرار، القيم السالبة، الكامبينات المستبعدة، الإعلانات اليتيمة |
| Metrics | `engine/metrics.py` | الأرقام | CPR, CTR, CPM, CVR, ROAS, Hook rate (3s/impr), Hold rate (ThruPlay/3s), LPV rate, ATC rate |
| Anomaly detection | `engine/anomaly.py` | إيه اللي اتغير امبارح بشكل غير طبيعي؟ | امبارح مقابل آخر 7 أيام: لازم **z-score** عالي **و** تغيير % كبير مع بعض. مؤشرات النسب (CPR/CVR) مش بتتحسب لو التحويلات أقل من 5 في اليوم لأنها ضوضاء إحصائية. قواعد ثابتة: توقف التوصيل، و"كليكات طبيعية ونتائج صفر" = **تراكينج قبل ما تلوم الإعلانات** |
| Campaign QA | `engine/qa.py` | فيه حاجة في الـ setup بتهدر فلوس؟ | إعلانات مرفوضة، Learning Limited، ميزانية أقل من 1× CPA، أكتر من 6 إعلانات في ad set، Frequency عالي، إعلان صرف 2× التارجت بدون نتيجة، مفيش UTM، EMQ ضعيف، Naming |
| Prepaid wallet | `engine/prepaid.py` | الأكونت هيقف إمتى؟ | Runway = الرصيد ÷ الحرق اليومي (الأعلى بين متوسط 3 أيام ومجموع الميزانيات). شحن مقترح يغطي 7 أيام. Spending limit مقترح. جدول سيولة لكل الأكونتات |
| Budget allocation | `engine/budget.py` | أزوّد/أقلل فين؟ | داخل الأكونت فقط (كل أكونت براند منفصل). Scale +20% لو CPR 7 أيام ≤ 0.85× التارجت و3 أيام تحت التارجت و≥10 نتائج. Cut لو ≥ 1.25×. **السكيل بيتلغي أوتوماتيك لو الرصيد أقل من 3 أيام أو فيه anomaly حرجة** |
| Pacing + Forecast | `budget.py`, `forecast.py` | هنقفل الشهر فين؟ | Run-rate آخر 7 أيام + اتجاه CPR الأسبوعي (انحدار خطي 14 يوم) |
| Creative analytics | `engine/creative.py` | إيه اللي بيكسب ولـيه؟ | تحليل منفصل حسب **Angle / Format / Hook / Offer** من اسم الإعلان. Win rate، نصيب الصرف، Hook rate. Insights: زوّد إيه وقلّل إيه، زاوية كسبانة بس مش واخدة صرف، Hook قوي وتحويل ضعيف = مشكلة Message match |
| Creative fatigue | `creative.py` | أي إعلان محتاج بديل؟ | CTR آخر 3 أيام نزل ≥30% عن أول الفترة **و** Frequency 7 أيام ≥ 3 |
| New-post triage | `creative.py` | البوست ده يستاهل ادز؟ وفين؟ | Score من 100 (تفاعل مقابل متوسط الصفحة 35، Share+Save 25، كومنتات فيها نية شراء 20، Retention 10، وضوح العرض/CTA 10). ≥75: إعلان — لو زاويته من أحسن زاويتين في الأكونت يدخل **كامبين السكيل الموجودة بالـ Post ID**، غير كده **اختبار** في كامبين الاختبار. 50–75: اختبار بحد صرف 2× CPA. أقل: عضوي |
| Testing system | `engine/testing.py` | الاختبار كسب؟ | معايير متحددة قبل الإطلاق: Winner = ≥5 نتائج و CPR ≤ 0.9×. Loser = صرف 2× بدون نتيجة أو CPR ≥ 1.5× بعد 3× صرف. أكتر من 10 أيام = Inconclusive |
| Test ideas | `creative.py` | نختبر إيه بعد كده؟ | فرضيات مش أفكار عشوائية: الزاوية الكسبانة بفورمات لسه متجربتش، الهوك الأعلى على زوايا تانية، بدايل للإعلانات المرهقة، زوايا المنافسين اللي شغالة من 30+ يوم |
| Competitors | `engine/competitor.py` | السوق بيعمل إيه؟ | مدة تشغيل الإعلان (مؤشر ربحية)، العروض المتكررة، زيادة مفاجئة في عدد الإعلانات |
| Search terms | `engine/search_terms.py` | (Google — Phase 2) | Negatives مقترحة، Exact match مقترحة، كلمات بتهدر فلوس |
| Actions | `pipeline.py` | أعمل إيه النهارده؟ | كل ما سبق بيتحول لقائمة واحدة P0–P3 مرتبة بـ Impact × Confidence ÷ Effort، ولكل بند: ليه، إزاي، المسؤول، الأداة، الموعد، KPI |
| Health score | `pipeline.py` | الأكونت عامل إزاي في رقم؟ | 100 ناقص: CPR فوق التارجت، ROAS تحت الـ break-even، الرصيد، الـ anomalies، الـ QA، الإرهاق. مديونية أو رصيد < يوم ونص = "محتاج تدخل" دايماً |
| Roadmap / Journal | `engine/roadmap.py` | وصلنا لفين؟ | مراحل + مهام + أحداث (إطلاق، قرار، نتيجة، مشكلة) بتأثير إيجابي/سلبي. السيستم بيضيف الأحداث المهمة لوحده (اختبار كسب، مديونية، تراكينج وقع) |

## "الفريق" جوه كل أكونت

| الدور | اللي السيستم بيعمله | اللي لسه على الإنسان |
|---|---|---|
| Media Buyer | Breakdown، anomalies، QA، قرارات الميزانية، مسار البوستات الجديدة | تنفيذ التعديلات في Ads Manager (أو `apply-spend-caps`) |
| Creative Strategist | Insights حسب Angle/Format/Hook، الإرهاق، أفكار اختبارات، تحليل البوست بـ Claude | الإنتاج |
| Tracking & Analytics | تنبيه وقوع التراكينج، EMQ، UTMs | إصلاح Pixel/CAPI/GTM |
| Finance / Account Manager | جدول الشحن، Spending limits، التنبؤ | الدفع |
| Reporting | CEO Layer + Team Layer + Roadmap يومياً | — |
| Competitor research | تحليل ملف Ad Library | تجميع الملف (أنظر القيود) |

### Phase 2 (مش مبني لسه — عشان محدش يفتكر إنه موجود)

- **TikTok / Snapchat / Google connectors:** المحرك مستقل عن المنصة (كل حاجة بتشتغل على `rows` موحدة)، فكل منصة محتاجة connector بيطلع نفس الشكل. **القواعد والـ thresholds لازم تتضبط لكل منصة** — متنقلش قواعد ميتا زي ما هي.
- **SEO + AEO Intelligence Agent**، **WhatsApp Campaign Optimization Agent** (ربط المحادثات بالمبيعات من CRM)، **Landing pages / GA4 audit:** مواصفات بس. الأقرب للتنفيذ: WhatsApp — محتاج مصدر بيانات بيقول كل محادثة انتهت ببيع ولا لأ، وبعدها CPR الحقيقي = الصرف ÷ المبيعات مش ÷ المحادثات.

## القيود اللي لازم تعرفها

- **Attribution:** الأرقام هي أرقام ميتا (7d click / 1d view). قارنها بالمتجر/CRM أسبوعياً؛ لو الفرق كبير الحكم على الـ CPR بيتغير.
- **Page/IG insights:** ميتا غيّرت أسماء مقاييس البوستات أكتر من مرة (2024–2025). الـ connector بيتعامل مع النقص من غير ما يقع، بس راجع `connectors/meta.py → posts()` لو التقييم طلع أصفار.
- **Ad Library API** خارج الاتحاد الأوروبي بترجع إعلانات سياسية بس. للسوق المصري الملف في `data/competitors/` بيتجمع يدوي أو بأداة scraping.
- **الرصيد المتاح في الدفع المسبق:** بيتقري من `funding_source_details.display_string`. لو الصيغة اتغيرت أو مش ظاهرة، حط `prepaid.manual_balance` في إعدادات الأكونت.
- **Anomaly detection** إحصائي: بيقولك "حصل تغيير غير طبيعي"، مش "السبب". الـ hint بيوجهك تبدأ تدور فين.

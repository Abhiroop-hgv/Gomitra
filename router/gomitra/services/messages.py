"""Farmer-facing text in English, Hindi and Telugu.

Gemini writes the message from the finding plus vet-document passages (so the advice is grounded).
If Gemini is unavailable the fixed templates below are used, so an alert is never blank.
"""
import json
import logging
import os

from gomitra.core import tracing as trace
LANGS = ("en", "hi", "te")
PROJECT = os.getenv("PROJECT", "cattle-id-511705")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "global")

TEMPLATES = {
    "lumpy": {
        "en": ("Needs attention", "The camera found lumps on {name}'s skin. This can be a sign of lumpy skin disease.",
               "Keep her away from the other cows and call your vet today."),
        "hi": ("ध्यान देने की ज़रूरत", "कैमरे को {name} की त्वचा पर गांठें दिखी हैं। यह लंपी स्किन रोग का संकेत हो सकता है।",
               "उसे दूसरी गायों से अलग रखें और आज ही पशु चिकित्सक को बुलाएं।"),
        "te": ("శ్రద్ధ అవసరం", "కెమెరాకు {name} చర్మంపై గడ్డలు కనిపించాయి. ఇది లంపీ స్కిన్ వ్యాధి సంకేతం కావచ్చు.",
               "దానిని ఇతర ఆవుల నుండి వేరుగా ఉంచి, ఈ రోజే పశు వైద్యుడికి కాల్ చేయండి."),
    },
    "fmd": {
        "en": ("Needs attention", "{name} shows signs that can match foot-and-mouth disease.",
               "Separate her now, do not move her, and call your vet and the animal husbandry office today."),
        "hi": ("ध्यान देने की ज़रूरत", "{name} में खुरपका-मुंहपका रोग जैसे लक्षण दिख रहे हैं।",
               "उसे अभी अलग करें, कहीं न ले जाएं, और आज ही पशु चिकित्सक व पशुपालन कार्यालय को बताएं।"),
        "te": ("శ్రద్ధ అవసరం", "{name}లో గాలికుంటు వ్యాధి (ఫుట్ అండ్ మౌత్) లాంటి లక్షణాలు కనిపిస్తున్నాయి.",
               "దానిని ఇప్పుడే వేరు చేయండి, ఎక్కడికీ తీసుకెళ్లకండి, ఈ రోజే పశు వైద్యుడికి మరియు పశుసంవర్ధక కార్యాలయానికి తెలియజేయండి."),
    },
    "distress": {
        "en": ("Possible distress call", "A cow near {name} made a loud distress-like call.",
               "Walk over and check the cows for injury, hunger, or a calf in trouble."),
        "hi": ("परेशानी की आवाज़ संभव", "{name} के पास किसी गाय ने तकलीफ जैसी तेज़ आवाज़ निकाली।",
               "जाकर गायों को देखें - चोट, भूख या बछड़े की परेशानी हो सकती है।"),
        "te": ("బాధతో అరుపు కావచ్చు", "{name} దగ్గర ఒక ఆవు బాధతో కూడిన పెద్ద అరుపు చేసింది.",
               "వెళ్లి ఆవులను చూడండి - గాయం, ఆకలి లేదా దూడకు ఇబ్బంది కావచ్చు."),
    },
    "limp": {
        "en": ("Needs attention", "{name} is walking unevenly and may be limping.",
               "Check her hoof and leg. Keep her on soft, dry ground. Call your vet if she is still limping tomorrow."),
        "hi": ("ध्यान देने की ज़रूरत", "{name} असमान चल रही है और लंगड़ा रही हो सकती है।",
               "उसके खुर और पैर की जांच करें। उसे नरम, सूखी जमीन पर रखें। कल भी लंगड़ाए तो पशु चिकित्सक को बुलाएं।"),
        "te": ("శ్రద్ధ అవసరం", "{name} అసమానంగా నడుస్తోంది, కుంటుతూ ఉండవచ్చు.",
               "దాని గిట్టలు, కాలు పరిశీలించండి. మెత్తని, పొడి నేలపై ఉంచండి. రేపు కూడా కుంటుతుంటే పశు వైద్యుడికి కాల్ చేయండి."),
    },
    "rest": {
        "en": ("Resting more than usual", "{name} has been lying down much more than usual in the last day.",
               "Check her for fever, sore feet or a sore udder, and see if she is eating. Call your vet if she also eats less or does not get up when you come near."),
        "hi": ("सामान्य से ज़्यादा आराम", "{name} पिछले एक दिन में सामान्य से बहुत ज़्यादा लेटी रही है।",
               "उसे बुखार, पैरों या थन में दर्द की जांच करें और देखें कि वह खा रही है या नहीं। अगर वह कम खाए या पास जाने पर भी न उठे तो पशु चिकित्सक को बुलाएं।"),
        "te": ("మామూలు కంటే ఎక్కువ విశ్రాంతి", "{name} గత ఒక రోజులో మామూలు కంటే చాలా ఎక్కువగా పడుకుని ఉంది.",
               "జ్వరం, కాళ్లు లేదా పొదుగు నొప్పి ఉందేమో చూడండి, తింటోందో లేదో గమనించండి. తక్కువ తింటున్నా, దగ్గరకు వెళ్లినా లేవకపోయినా పశు వైద్యుడికి కాల్ చేయండి."),
    },
    "down": {
        "en": ("Down for hours", "{name} has been lying down for hours without standing up.",
               "Go and look at her now. Check that she can stand and is breathing normally. Call your vet today if she cannot or will not get up."),
        "hi": ("कई घंटों से लेटी है", "{name} कई घंटों से बिना खड़े हुए लेटी है।",
               "अभी जाकर उसे देखें। जांचें कि वह खड़ी हो सकती है और सामान्य सांस ले रही है। अगर वह खड़ी न हो सके या न हो, तो आज ही पशु चिकित्सक को बुलाएं।"),
        "te": ("గంటలుగా పడుకుని ఉంది", "{name} నిలబడకుండా గంటలుగా పడుకుని ఉంది.",
               "ఇప్పుడే వెళ్లి చూడండి. అది నిలబడగలదో, సాధారణంగా శ్వాస తీసుకుంటోందో చూడండి. నిలబడలేకపోతే లేదా నిలబడకపోతే ఈ రోజే పశు వైద్యుడికి కాల్ చేయండి."),
    },
    "eating": {
        "en": ("Eating less than usual", "Chewing near {name} was much lower than usual in the last day.",
               "Check the feed and water. Look for a cow standing apart or not chewing. Call your vet if any cow is not eating at all."),
        "hi": ("सामान्य से कम खा रही हैं", "पिछले एक दिन में {name} के पास चबाना सामान्य से बहुत कम रहा।",
               "चारा और पानी जांचें। देखें कि कोई गाय अलग खड़ी है या चबा नहीं रही। कोई गाय बिल्कुल न खा रही हो तो पशु चिकित्सक को बुलाएं।"),
        "te": ("మామూలు కంటే తక్కువ తింటున్నాయి", "గత ఒక రోజులో {name} దగ్గర నమలడం మామూలు కంటే చాలా తక్కువగా ఉంది.",
               "మేత, నీళ్లు చూడండి. వేరుగా నిలబడిన లేదా నమలని ఆవు ఉందేమో చూడండి. ఏ ఆవైనా అసలు తినకపోతే పశు వైద్యుడికి కాల్ చేయండి."),
    },
    "healthy": {
        "en": ("Healthy", "Nothing unusual seen today.", ""),
        "hi": ("स्वस्थ", "आज कुछ असामान्य नहीं दिखा।", ""),
        "te": ("ఆరోగ్యంగా ఉంది", "ఈ రోజు అసాధారణంగా ఏమీ కనిపించలేదు.", ""),
    },
}

SHORT = {   # one-line label on the herd tile
    "lumpy": {"en": "Lumps on skin", "hi": "त्वचा पर गांठें", "te": "చర్మంపై గడ్డలు"},
    "fmd": {"en": "Mouth and foot signs", "hi": "मुंह और खुरों के लक्षण", "te": "నోరు, కాళ్ల లక్షణాలు"},
    "limp": {"en": "Limping", "hi": "लंगड़ापन", "te": "కుంటుతోంది"},
    "distress": {"en": "Loud distress call", "hi": "तकलीफ की आवाज़", "te": "బాధతో అరుపు"},
    "rest": {"en": "Resting more than usual", "hi": "ज़्यादा आराम कर रही है", "te": "ఎక్కువ విశ్రాంతి"},
    "down": {"en": "Lying for hours", "hi": "कई घंटों से लेटी है", "te": "గంటలుగా పడుకుని ఉంది"},
    "eating": {"en": "Eating less than usual", "hi": "कम खा रही हैं", "te": "తక్కువ తింటున్నాయి"},
}

FACTS = {
    "lumpy": "The camera found skin lumps; this can be lumpy skin disease (a contagious viral disease of cattle).",
    "fmd": "The camera found signs that can match foot-and-mouth disease (a highly contagious, notifiable disease).",
    "limp": "The walking check found uneven steps, which can mean lameness (a limp). Cause unknown.",
    "distress": "A loud distress-like call was heard near the cow(s). Cause unknown.",
    "rest": "The camera saw her lying down much more than her own usual amount over the last 24 hours. Cause unknown; it is a change from her normal, not a diagnosis.",
    "down": "The camera has seen her lying down at every sighting for several hours without standing. Cause unknown; it is a change from normal, not a diagnosis.",
    "eating": "Chewing sounds near this camera group were much lower than the usual daily amount. Cause unknown. The sound cannot say which cow, so this is a group alert.",
}


def template(kind, name):
    out = {}
    for lang in LANGS:
        title, text, advice = TEMPLATES[kind][lang]
        out[lang] = {"title": title, "text": text.format(name=name), "advice": advice}
    return out


def _gemini_client():
    from google import genai
    from google.genai import types
    return genai.Client(vertexai=True, project=PROJECT, location=GEMINI_LOCATION,
                        http_options=types.HttpOptions(timeout=25000)), types


def compose(kind, name, passages=(), severity="medium", confidence=None, use_gemini=True):
    """-> ({"en": {"title","text","advice"}, "hi": ..., "te": ...}, "gemini" | "template")."""
    base = template(kind, name)
    if not use_gemini or kind == "healthy":
        return base, "template"
    try:
        client, types = _gemini_client()
        ctx = "\n".join(f"[{i + 1}] ({p['source']}) {p['text']}" for i, p in enumerate(passages)) or "(no passages found)"
        prompt = f"""You write alerts for an Indian dairy farmer. Be calm, short and clear (grade 5 reading level).
Facts: {FACTS[kind]} Animal: {name}. Severity: {severity}. Model confidence: {confidence}.
Vet passages (use ONLY these for advice; if empty, give only the safe default steps):
{ctx}

Rules:
- Say what was seen in one sentence ("text"). In "advice" give 3 short numbered steps taken from the vet passages (separate the animal, who to call, what to avoid), one sentence each. No drug names and no doses.
- This is a screening alert, not a diagnosis. For medium or high severity, tell the farmer to call a vet.
- Mention isolating the animal for contagious diseases (lumpy skin, foot-and-mouth).
- If you used a passage, end the advice with its source in brackets, e.g. [source name].
Return JSON: {{"en": {{"title","text","advice"}}, "hi": {{...}}, "te": {{...}}}}.
"hi" must be Hindi in Devanagari and "te" must be Telugu in Telugu script. "title" is at most 4 words.
Safe default: {base['en']['advice']}"""
        with trace.step("Gemini on Vertex AI", f"{GEMINI_MODEL}, alert text in 3 languages"):
            r = client.models.generate_content(model=GEMINI_MODEL, contents=prompt,
                                               config=types.GenerateContentConfig(response_mime_type="application/json",
                                                                                  temperature=0.2))
        data = json.loads(r.text)
        for lang in LANGS:       # keep the template for any language the model left incomplete
            d = data.get(lang) or {}
            if not all(isinstance(d.get(k), str) and d[k].strip() for k in ("title", "text", "advice")):
                data[lang] = base[lang]
        return {lang: data[lang] for lang in LANGS}, "gemini"
    except Exception:
        logging.getLogger("gomitra").exception("gemini message failed, using template")
        return base, "template"
